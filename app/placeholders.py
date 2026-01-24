import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Match

import httpx

from .config import get_settings
from .commentary import (
    CommentarySource,
    fetch_commentary_for_reference,
)
from .scripture import (
    ScriptureLookupError,
    ScriptureLookupOptions,
    ScriptureVersion,
    fetch_scripture,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_strongs_dictionary() -> dict:
    """Load the Strong's Greek dictionary from the embedded JSON file."""
    dict_path = Path(__file__).parent / "strongs_greek.json"
    if dict_path.exists():
        with open(dict_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

PLACEHOLDER_PATTERN = re.compile(
    r"\[\[\s*scripture\s*:\s*([^\]]+?)\s*\]\]",
    re.IGNORECASE
)

# Global set to collect Strong's numbers during processing
_collected_strongs: set[str] = set()

# Global set to collect scripture references during processing
_collected_references: set[str] = set()


def get_collected_strongs() -> set[str]:
    """Return the collected Strong's numbers from processing."""
    return _collected_strongs.copy()


def clear_collected_strongs() -> None:
    """Clear the collected Strong's numbers."""
    _collected_strongs.clear()


def get_collected_references() -> set[str]:
    """Return the collected scripture references from processing."""
    return _collected_references.copy()


def clear_collected_references() -> None:
    """Clear the collected scripture references."""
    _collected_references.clear()


class ScripturePlaceholderError(Exception):
    """Raised when a scripture placeholder cannot be processed."""


@dataclass
class PlaceholderSpec:
    raw: str
    reference: str
    version: ScriptureVersion
    options: ScriptureLookupOptions
    nolinks: bool = False


def _parse_bool(value: str) -> bool:
    val = value.strip().lower()
    if val in {"true", "1", "yes", "y", "on"}:
        return True
    if val in {"false", "0", "no", "n", "off"}:
        return False
    raise ScripturePlaceholderError(f"Invalid boolean value '{value}' in scripture placeholder.")


def _parse_spec(raw_spec: str) -> PlaceholderSpec:
    parts = [p.strip() for p in raw_spec.split("|")]
    if not parts or not parts[0]:
        raise ScripturePlaceholderError("Scripture placeholder is missing a reference.")

    reference = parts[0]
    version = ScriptureVersion.ESV
    options = {
        "headings": False,
        "verses": True,
        "footnotes": False,
        "copyright": True,
        "nolinks": False,
    }

    if len(parts) > 1 and parts[1]:
        try:
            version = ScriptureVersion(parts[1].upper())
        except ValueError:
            raise ScripturePlaceholderError(f"Unsupported scripture version '{parts[1]}'.")

    for opt in parts[2:]:
        if not opt:
            continue
        if "=" not in opt:
            raise ScripturePlaceholderError(
                f"Invalid option '{opt}' in scripture placeholder. Use key=value."
            )
        key, value = opt.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if key in {"headings", "include_headings"}:
            options["headings"] = _parse_bool(value)
        elif key in {"verses", "verse_numbers", "include_verse_numbers"}:
            options["verses"] = _parse_bool(value)
        elif key in {"footnotes", "include_footnotes"}:
            options["footnotes"] = _parse_bool(value)
        elif key in {"copyright", "include_short_copyright"}:
            options["copyright"] = _parse_bool(value)
        elif key in {"nolinks", "no_links"}:
            options["nolinks"] = _parse_bool(value)
        else:
            raise ScripturePlaceholderError(f"Unknown option '{key}' in scripture placeholder.")

    lookup_opts = ScriptureLookupOptions(
        include_headings=options["headings"],
        include_verse_numbers=options["verses"],
        include_footnotes=options["footnotes"],
        include_short_copyright=options["copyright"],
    )

    return PlaceholderSpec(
        raw=raw_spec,
        reference=reference,
        version=version,
        options=lookup_opts,
        nolinks=options["nolinks"],
    )


def _extract_chapter(reference: str) -> str | None:
    """Best-effort extraction of a chapter number from a reference string."""
    colon_match = re.search(r"(\d+)\s*:\s*\d+", reference)
    if colon_match:
        return colon_match.group(1)

    numbers = re.findall(r"\b(\d+)\b", reference)
    if not numbers:
        return None

    if len(numbers) == 1:
        return numbers[0]

    # If multiple numbers exist (e.g., "1 John 3:16"), the chapter is usually the penultimate number.
    return numbers[-2]


def _format_scripture_body(
    reference: str,
    text: str,
    include_verse_numbers: bool,
    include_footnotes: bool,
    nolinks: bool = False,
) -> str:
    """
    Convert plain text with verse numbers into scripture.sty macros.

    - Adds \\ch{#} for the chapter at the start (best-effort from reference).
    - Converts verse numbers at line starts into \\vs{#}.
    - Handles NET Bible format with <b>chapter:verse</b> tags.
    """
    def strip_heading_and_footnotes(raw: str) -> str:
        lines = raw.splitlines()

        # Drop leading blanks
        while lines and not lines[0].strip():
            lines.pop(0)

        # Drop heading (first non-empty line without digits)
        if lines and not re.search(r"\d", lines[0]):
            lines.pop(0)

        # Drop blank lines after heading
        while lines and not lines[0].strip():
            lines.pop(0)

        # Trim footnotes section
        for idx, line in enumerate(lines):
            if line.strip().lower() == "footnotes":
                lines = lines[:idx]
                break

        # Drop trailing blanks
        while lines and not lines[-1].strip():
            lines.pop()

        cleaned = "\n".join(lines)

        if not include_footnotes:
            cleaned = re.sub(r"\(\d+\)", "", cleaned)

        # Remove trailing translation label like "(ESV)"
        cleaned = re.sub(r"\s*\([A-Za-z]{2,}\)\s*$", "", cleaned)

        return cleaned

    clean = strip_heading_and_footnotes(text)

    # Remove NET footnote markers <n id="X" />
    clean = re.sub(r'<n\s+id="\d+"\s*/>', '', clean)

    # Handle NET verse reference spans: <span class="vref"><b>3:<span class="verseNumber">2</span></b></span>
    vref_pattern = re.compile(r'<span class="vref"><b>(\d+):<span class="verseNumber">(\d+)</span></b></span>\s*')

    def vref_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            verse_num = match.group(2)
            return f"\\vs{{{verse_num}}} "
        return ""

    clean = vref_pattern.sub(vref_repl, clean)

    # Handle NET subsequent verse spans: <span class="vref"><b><span class="verseNumber">4</span></b></span>
    vref_subsequent_pattern = re.compile(r'<span class="vref"><b><span class="verseNumber">(\d+)</span></b></span>\s*')

    def vref_subsequent_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            verse_num = match.group(1)
            return f"\\vs{{{verse_num}}} "
        return ""

    clean = vref_subsequent_pattern.sub(vref_subsequent_repl, clean)

    # Handle NET Bible format: <b>chapter:verse</b> -> \vs{verse} (first verse, simple format)
    net_first_verse_pattern = re.compile(r"<b>(\d+):(\d+)</b>\s*")

    def net_first_verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            verse_num = match.group(2)
            return f"\\vs{{{verse_num}}} "
        return ""

    clean = net_first_verse_pattern.sub(net_first_verse_repl, clean)

    # Handle NET Bible format: <b>verse</b> -> \vs{verse} (subsequent verses, simple format)
    net_verse_pattern = re.compile(r"<b>(\d+)</b>\s*")

    def net_verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            verse_num = match.group(1)
            return f"\\vs{{{verse_num}}} "
        return ""

    clean = net_verse_pattern.sub(net_verse_repl, clean)

    # Handle Strong's numbers: <st data-num="XXXX" class="">word</st> -> \hyperlink{strongs-XXXX}{word}
    # If nolinks=True, just output the word without hyperlink (for paracol compatibility)
    strongs_pattern = re.compile(r'<st data-num="(\d+)"[^>]*>([^<]+)</st>')

    def strongs_repl(match: Match[str]) -> str:
        strongs_num = match.group(1)
        word = match.group(2)
        _collected_strongs.add(strongs_num)
        if nolinks:
            return word
        return f"\\hyperlink{{strongs-{strongs_num}}}{{{word}}}"

    clean = strongs_pattern.sub(strongs_repl, clean)

    # Also handle ESV format: verse numbers at line starts like "[1]" or "1 "
    verse_pattern = re.compile(r"(^|\s)\[?(\d+)\]?\s+", re.MULTILINE)

    def verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            return f"{match.group(1)}\\vs{{{match.group(2)}}} "
        return match.group(1)

    converted = verse_pattern.sub(verse_repl, clean)

    if include_verse_numbers:
        chapter = _extract_chapter(reference)
        if chapter:
            converted = f"\\ch{{{chapter}}}\n" + converted

    # Strip any remaining HTML tags that weren't specifically handled
    converted = re.sub(r'<[^>]+>', '', converted)

    # Clean up multiple spaces
    converted = re.sub(r'  +', ' ', converted)

    return converted


SCRIPTURE_ANALYSIS_PROMPT = '''Analyze this Bible passage and apply LaTeX formatting:

1. **Poetry Detection**: Identify portions that are Hebrew poetry (parallelism, elevated speech, divine pronouncements, blessings, curses, prophetic oracles, songs). Wrap ONLY the poetic portions in \\begin{poetry} and \\end{poetry} tags. Common poetic sections include:
   - God speaking in formal/elevated language (like Genesis 3:14-19)
   - Blessings and curses
   - Prophetic pronouncements
   - Songs and hymns embedded in narrative

2. **Divine Name Tagging**: When "the Lord" or "the LORD" or "LORD" refers to God (YHWH), replace it with \\name{Lord}. Do NOT tag when "lord" refers to a human master.

IMPORTANT RULES:
- Return ONLY the modified scripture text, nothing else
- Preserve all existing LaTeX commands (\\vs{}, \\ch{}, \\hyperlink{}, etc.)
- Do NOT wrap entire passages as poetry if only portions are poetic
- If no poetry is detected, return the text unchanged except for \\name{Lord} tags
- Maintain exact spacing and line breaks

Scripture text:
'''


async def _analyze_scripture_with_ai(text: str, reference: str) -> str:
    """
    Use Claude API to detect poetic portions and tag divine names.
    Falls back to original text if API call fails.
    """
    settings = get_settings()
    api_key = settings.anthropic_api_key

    if not api_key:
        logger.debug("No Anthropic API key, skipping scripture analysis")
        return text

    logger.info("AI analyzing scripture: %s", reference)

    request_body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": f"{SCRIPTURE_ANALYSIS_PROMPT}\n\nReference: {reference}\n\n{text}"
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=request_body,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

        data = response.json()
        content_blocks = data.get("content", [])

        if content_blocks:
            for block in content_blocks:
                if block.get("type") == "text":
                    result = block.get("text", "").strip()
                    if result:
                        has_poetry = r"\begin{poetry}" in result
                        has_name = r"\name{" in result
                        logger.info("AI result for %s: poetry=%s, name_tags=%s", reference, has_poetry, has_name)
                        return result

        logger.warning("AI returned empty result for %s", reference)
        return text
    except Exception as exc:
        logger.warning("Scripture AI analysis failed for %s: %s", reference, exc)
        return text


def _render_scripture(result_ref: str, version: ScriptureVersion, text: str) -> str:
    r"""
    Wrap fetched text in the scripture environment from the scripture package.
    Uses \scripturefont to ensure scripture uses serif font, not main document font.
    Poetry detection and divine name tagging are handled by AI analysis.
    """
    reference_arg = result_ref.replace("[", "").replace("]", "")
    version_arg = f"[version={version.value}]" if version else ""
    body = text.strip()

    return (
        f"\\begin{{scripture}}[{reference_arg}]{version_arg}\n"
        f"\\scripturefont\n"
        f"{body}\n"
        f"\\end{{scripture}}"
    )


def _ensure_scripture_package(main_path: Path) -> None:
    """
    Ensure the scripture package is loaded in the main TeX file.
    """
    try:
        content = main_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = main_path.read_text(errors="replace")

    if "usepackage{scripture}" in content or "usepackage[parindent" in content:
        return

    insertion = "\\usepackage{scripture}\n"
    documentclass_pattern = re.compile(r"(\\documentclass[^\\n]*\n)", re.IGNORECASE)
    match = documentclass_pattern.search(content)

    if match:
        idx = match.end()
        content = content[:idx] + insertion + content[idx:]
    else:
        content = insertion + content

    main_path.write_text(content, encoding="utf-8")


def _escape_latex_text(text: str) -> str:
    """Escape special LaTeX characters in definition text."""
    if not text:
        return ""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def generate_strongs_appendix(strongs_numbers: set[str]) -> str:
    """
    Generate a LaTeX appendix section with Strong's number definitions.
    Uses embedded public domain Strong's dictionary.
    """
    if not strongs_numbers:
        return ""

    strongs_dict = _load_strongs_dictionary()

    lines = [
        r"\newpage",
        r"\section*{Greek Word Study}",
        r"\addcontentsline{toc}{section}{Greek Word Study}",
        r"",
        r"\begin{description}",
    ]

    # Sort numerically
    sorted_nums = sorted(strongs_numbers, key=lambda x: int(x))

    for num in sorted_nums:
        entry = strongs_dict.get(num, {})
        greek = entry.get('greek', '')
        translit = entry.get('translit', '')
        definition = _escape_latex_text(entry.get('def', 'Definition not available'))

        # Build the entry line with Greek in parentheses using Greek font (not bold)
        label = f"G{num}"
        if greek:
            label += f" ({{\\textnormal{{\\greekfont {greek}}}}})"

        lines.append(
            rf"\item[\hypertarget{{strongs-{num}}}{{{label}}}] "
            rf"\textbf{{{translit}}} --- {definition}"
        )

    lines.append(r"\end{description}")

    return "\n".join(lines)


async def generate_commentary_appendix(
    references: set[str],
    sources: list[CommentarySource]
) -> str:
    """
    Generate a LaTeX appendix section with commentary from classic commentators.

    Args:
        references: Set of scripture references to fetch commentary for
        sources: List of CommentarySource values to include

    Returns:
        LaTeX string for the commentary appendix
    """
    if not references or not sources:
        return ""

    lines = [
        r"\newpage",
        r"\section*{Commentary Notes}",
        r"\addcontentsline{toc}{section}{Commentary Notes}",
        r"",
    ]

    # Sort references for consistent ordering
    sorted_refs = sorted(references)

    for ref in sorted_refs:
        ref_has_content = False
        ref_lines = []

        for source in sources:
            result = await fetch_commentary_for_reference(ref, source)
            if result and result.entries:
                if not ref_has_content:
                    # First time we have content for this reference
                    ref_lines.append(rf"\subsection*{{{_escape_latex_text(ref)}}}")
                    ref_lines.append("")
                    ref_has_content = True

                # Add source heading
                source_name = result.source_name
                ref_lines.append(rf"\paragraph{{{_escape_latex_text(source_name)}}}")
                ref_lines.append("")

                # Add commentary text (just the first entry for verse-level)
                entry = result.entries[0]
                text = entry.text

                # Truncate very long commentary for the appendix
                if len(text) > 2000:
                    text = text[:2000] + "..."

                # Escape and format the text
                escaped_text = _escape_latex_text(text)
                # Preserve paragraph breaks
                escaped_text = escaped_text.replace('\n\n', '\n\n\\par\n')

                ref_lines.append(escaped_text)
                ref_lines.append("")

        if ref_has_content:
            lines.extend(ref_lines)

    # Only return content if we actually got any commentary
    if len(lines) > 4:  # More than just the header
        return "\n".join(lines)

    return ""


async def process_scripture_placeholders(
    work_dir: Path,
    main_file: str,
    include_commentary: bool = False,
    commentary_sources: list[CommentarySource] | None = None
) -> None:
    """
    Replace scripture placeholders in all .tex files under work_dir.

    Placeholder syntax:
      [[scripture:<reference>|<version>|headings=true|verses=true|footnotes=false|copyright=true]]
    Version defaults to ESV. Options are optional.

    Args:
        work_dir: Working directory containing .tex files
        main_file: Name of the main .tex file
        include_commentary: Whether to generate commentary appendix
        commentary_sources: List of commentary sources to include
    """
    # Clear collected data from previous runs
    clear_collected_strongs()
    clear_collected_references()

    tex_files = list(work_dir.rglob("*.tex"))
    if not tex_files:
        return

    placeholder_specs: dict[str, PlaceholderSpec] = {}
    file_placeholders: dict[Path, list[tuple[str, str]]] = {}

    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = tex_file.read_text(errors="replace")

        matches = list(PLACEHOLDER_PATTERN.finditer(content))
        if not matches:
            continue

        pairs: list[tuple[str, str]] = []
        for m in matches:
            placeholder_text = m.group(0)
            spec_text = m.group(1).strip()
            pairs.append((placeholder_text, spec_text))
            if spec_text not in placeholder_specs:
                placeholder_specs[spec_text] = _parse_spec(spec_text)

        file_placeholders[tex_file] = pairs

    if not placeholder_specs:
        return

    replacements: dict[str, str] = {}
    errors: list[str] = []

    for spec in placeholder_specs.values():
        try:
            result = await fetch_scripture(spec.reference, spec.version, spec.options)
            formatted = _format_scripture_body(
                result.canonical or result.reference,
                result.text,
                spec.options.include_verse_numbers,
                spec.options.include_footnotes,
                spec.nolinks,
            )
            # Apply AI analysis to detect poetry and tag divine names
            analyzed = await _analyze_scripture_with_ai(
                formatted,
                result.canonical or result.reference
            )
            rendered = _render_scripture(result.canonical or result.reference, spec.version, analyzed)
            replacements[spec.raw] = rendered
            # Collect reference for commentary appendix
            _collected_references.add(result.canonical or spec.reference)
        except ScriptureLookupError as exc:
            errors.append(f"{spec.reference} ({spec.version.value}): {exc}")
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected error while fetching scripture for %s", spec.reference)
            errors.append(f"{spec.reference} ({spec.version.value}): {exc}")

    if errors:
        raise ScripturePlaceholderError(
            "Failed to fetch scripture for: " + "; ".join(errors)
        )

    for tex_file, pairs in file_placeholders.items():
        try:
            content = tex_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = tex_file.read_text(errors="replace")

        for placeholder_text, raw_key in pairs:
            replacement = replacements.get(raw_key)
            if not replacement:
                continue
            content = content.replace(placeholder_text, replacement)

        tex_file.write_text(content, encoding="utf-8")

    # Ensure the scripture package is available in the main TeX file
    main_path = work_dir / main_file
    if main_path.exists():
        _ensure_scripture_package(main_path)

        try:
            content = main_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = main_path.read_text(errors="replace")

        appendices = []

        # Note: Strong's appendix is now generated in sermon_latex.py from NET Bible data

        # Add commentary appendix if requested and references were collected
        if include_commentary and commentary_sources:
            refs = get_collected_references()
            if refs:
                commentary_appendix = await generate_commentary_appendix(refs, commentary_sources)
                if commentary_appendix:
                    appendices.append(commentary_appendix)

        # Insert appendices before \end{document}
        if appendices and r"\end{document}" in content:
            all_appendices = "\n\n".join(appendices)
            content = content.replace(
                r"\end{document}",
                f"\n{all_appendices}\n\\end{{document}}"
            )
            main_path.write_text(content, encoding="utf-8")
    else:
        logger.warning("Main TeX file %s not found when ensuring scripture package", main_file)
