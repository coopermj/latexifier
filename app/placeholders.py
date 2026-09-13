import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Match

import httpx

from .anthropic_config import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_MESSAGES_URL,
    ANTHROPIC_MODEL,
)
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
_re_open_dquote = re.compile(r'(?:(?<=[\s(])|^)"(?=\S)', re.MULTILINE)
_re_verse_open_dquote = re.compile(r'(\\(?:vs|ch)\{\d+\}\s*)["\u201d](?=\S)')
_re_open_squote = re.compile(r"(?:(?<=[\s(])|^)'(?=\S)", re.MULTILINE)
_re_wrong_open_squote = re.compile(r'(?:(?<=[\s(])|^)\u2019(?=\S)', re.MULTILINE)

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


def _smart_scripture_quotes(text: str) -> str:
    """Convert straight scripture quotes to Unicode curly quotes."""
    # Verse spacing belongs to TeX, so AI output can put the opening quote
    # directly after the marker. Also repair right quotes from older output.
    text = _re_verse_open_dquote.sub(lambda m: m.group(1) + '\u201c', text)
    text = _re_open_dquote.sub('\u201c', text)
    text = text.replace('"', '\u201d')
    text = _re_open_squote.sub('\u2018', text)
    text = _re_wrong_open_squote.sub('\u2018', text)
    text = text.replace("'", '\u2019')
    return text


@dataclass
class PlaceholderSpec:
    raw: str
    reference: str
    version: ScriptureVersion
    options: ScriptureLookupOptions
    nolinks: bool = False
    strongs_overlay: bool = False


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
        "headings": True,
        "verses": True,
        "footnotes": False,
        "copyright": True,
        "nolinks": False,
        "strongs_overlay": False,
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
        elif key in {"strongs_overlay", "strongs"}:
            options["strongs_overlay"] = _parse_bool(value)
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
        strongs_overlay=options["strongs_overlay"],
    )


def _extract_chapter(reference: str) -> str | None:
    """Best-effort extraction of a chapter number from a reference string."""
    chapter_range = _extract_chapter_range(reference)
    if chapter_range:
        return str(chapter_range[0])

    numbers = re.findall(r"\b(\d+)\b", reference)
    if not numbers:
        return None

    if len(numbers) == 1:
        return numbers[0]

    # If multiple numbers exist (e.g., "1 John 3:16"), the chapter is usually the penultimate number.
    return numbers[-2]


def _extract_chapter_range(reference: str) -> tuple[int, int] | None:
    """Best-effort extraction of start/end chapters from a scripture reference."""
    normalized = (
        reference.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    normalized = re.sub(r"^\s*[1-3]\s+", "", normalized)
    start_match = re.search(r"\b(\d+)(?::\d+)?", normalized)
    if not start_match:
        return None

    start_chapter = int(start_match.group(1))
    end_chapter = start_chapter
    tail = normalized[start_match.end():]
    dash_match = re.search(r"-\s*(\d+)(?::(\d+))?", tail)

    if dash_match:
        if dash_match.group(2):
            end_chapter = int(dash_match.group(1))
        elif ":" not in start_match.group(0):
            end_chapter = int(dash_match.group(1))

    return start_chapter, end_chapter


def _insert_chapter_markers_at_verse_resets(
    text: str,
    chapter_range: tuple[int, int] | None,
) -> str:
    """Insert chapter markers when verse numbers reset in a cross-chapter range."""
    if not chapter_range:
        return text

    current_chapter, end_chapter = chapter_range
    if end_chapter <= current_chapter:
        return text

    seen_verse = False
    previous_verse = 0

    def repl(match: Match[str]) -> str:
        nonlocal current_chapter, previous_verse, seen_verse
        verse = int(match.group(1))
        prefix = ""
        if seen_verse and verse <= previous_verse and current_chapter < end_chapter:
            current_chapter += 1
            prefix = f"\\ch{{{current_chapter}}}\n"
        seen_verse = True
        previous_verse = verse
        return prefix + match.group(0)

    return re.sub(r"\\vs\{(\d+)\}", repl, text)


def _format_scripture_body(
    reference: str,
    text: str,
    include_verse_numbers: bool,
    include_footnotes: bool,
    nolinks: bool = False,
    include_headings: bool = True,
) -> str:
    """
    Convert plain text with verse numbers into scripture.sty macros.

    - Adds \\ch{#} for the chapter at the start (best-effort from reference).
    - Converts verse numbers at line starts into \\vs{#}.
    - Handles NET Bible format with <b>chapter:verse</b> tags.
    """
    is_html = bool(re.search(r"</?(?:p|h\d|span|b)\b", text, re.IGNORECASE))

    def _heading_tex(h: str) -> str:
        return f"\\heading{{{h}}}\n"

    def strip_heading_and_footnotes(raw: str) -> str:
        lines = raw.splitlines()

        # Drop leading blanks
        while lines and not lines[0].strip():
            lines.pop(0)

        # Handle heading (first non-empty line without digits)
        if not is_html and lines and not re.search(r"\d", lines[0]):
            heading = lines.pop(0).strip()
            if include_headings and heading:
                lines.insert(0, _heading_tex(heading))

        # Drop blank lines after heading (only when no heading was inserted)
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

    # HTML paragraphs must survive tag stripping; otherwise NET verses from
    # separate paragraphs are silently joined into one continuous paragraph.
    clean = re.sub(r"</p\s*>\s*", "\n\n", clean, flags=re.IGNORECASE)
    # NET starts each poetry line with <p class="poetry"> but often omits
    # </p>. Keep those opening boundaries too, or adjacent words get joined.
    clean = re.sub(r"<p\b[^>]*>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<br\b[^>]*>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\n{3,}", "\n\n", clean)

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

    # Also handle ESV/plain-text verse numbers. Bracketed verse numbers may be
    # inline; bare numbers are only verse markers at the start of a line.
    bracketed_verse_pattern = re.compile(r"\[(\d+)\]\s+")

    def bracketed_verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            return f"\\vs{{{match.group(1)}}} "
        return ""

    converted = bracketed_verse_pattern.sub(bracketed_verse_repl, clean)

    line_start_verse_pattern = re.compile(r"(?m)^([ \t]*)(\d+)\s+")

    def line_start_verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            return f"{match.group(1)}\\vs{{{match.group(2)}}} "
        return match.group(1)

    converted = line_start_verse_pattern.sub(line_start_verse_repl, converted)

    if include_verse_numbers:
        chapter_range = _extract_chapter_range(reference)
        converted = _insert_chapter_markers_at_verse_resets(converted, chapter_range)

    # Handle NET section headings (<h3>, <h4>, etc.) before catch-all strip
    heading_tag_re = re.compile(r'<h\d[^>]*>(.*?)</h\d>', re.DOTALL | re.IGNORECASE)
    if include_headings:
        converted = heading_tag_re.sub(
            lambda m: _heading_tex(re.sub(r'<[^>]+>', '', m.group(1)).strip()),
            converted,
        )
    else:
        converted = heading_tag_re.sub('', converted)

    # Strip any remaining HTML tags that weren't specifically handled
    converted = re.sub(r'<[^>]+>', '', converted)

    # Format mid-passage ESV headings: isolated short paragraphs with no digits
    # or LaTeX commands (these survive as plain text when include-headings=true)
    if include_headings and not is_html:
        converted = re.sub(
            r'\n\n([A-Z][^0-9\\\n]{4,70})\n\n',
            lambda m: f'\n\n{_heading_tex(m.group(1).strip())}\n',
            converted,
        )

    converted = _smart_scripture_quotes(converted)

    if include_verse_numbers:
        chapter = str(chapter_range[0]) if chapter_range else _extract_chapter(reference)
        if chapter:
            # Put the chapter after any opening heading, next to its first verse.
            first_verse = converted.find(r"\vs{")
            pos = first_verse if first_verse >= 0 else 0
            converted = converted[:pos].rstrip() + ("\n" if pos else "") + f"\\ch{{{chapter}}}\n" + converted[pos:]

    # Clean up multiple spaces
    converted = re.sub(r'  +', ' ', converted)

    return re.sub(r"(\\vs\{\d+\})\s+", r"\1", converted).strip()


def _extract_strongs_word_map(html_text: str) -> list[tuple[str, str]]:
    """Extract unique (strongs_num, net_word) pairs from NET HTML in first-occurrence order."""
    pattern = re.compile(r'<st data-num="(\d+)"[^>]*>([^<]+)</st>')
    results = []
    seen: set[str] = set()
    for m in pattern.finditer(html_text):
        num = m.group(1)
        if num not in seen:
            results.append((num, m.group(2).strip()))
            seen.add(num)
    return results


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
- Do NOT alter any punctuation, quotation marks, or non-structural characters — copy them byte-for-byte
- Maintain exact spacing and line breaks
- Keep all \\heading{...} commands OUTSIDE poetry environments; end poetry before a heading and restart it afterward if needed

Scripture text:
'''


def _scripture_content_tokens(text: str) -> list[str]:
    """Compare scripture words and numbers while ignoring formatting wrappers."""
    text = re.sub(r"\\(?:begin|end)\{poetry\}", "", text)
    text = re.sub(r"\\hyperlink\{strongs-\d+\}", "", text)
    text = re.sub(r"\\[A-Za-z]+\*?", "", text)
    return re.findall(r"\w+", text.casefold())


async def _analyze_scripture_with_ai(
    text: str,
    reference: str,
    strongs_word_map: list[tuple[str, str]] | None = None,
) -> str:
    """
    Use Claude API to detect poetic portions and tag divine names.
    When strongs_word_map is provided, also annotates ESV words with \\hyperlink commands.
    Falls back to original text if API call fails.
    """
    settings = get_settings()
    api_key = settings.anthropic_api_key

    if not api_key:
        logger.debug("No Anthropic API key, skipping scripture analysis")
        return text

    logger.info("AI analyzing scripture: %s (strongs_overlay=%s)", reference, strongs_word_map is not None)

    if strongs_word_map:
        strongs_list = "\n".join(f"G{num}: \"{word}\"" for num, word in strongs_word_map)
        prompt = (
            SCRIPTURE_ANALYSIS_PROMPT
            + "\n3. **Strong's Number Links**: The NET Bible renders the same passage with Greek word tags. "
            "Below is a list of `G<num>: \"<NET rendering>\"` mappings for this passage. "
            "For each content word (noun, verb, adjective, adverb) in the ESV text that corresponds "
            "to one of these Greek words, wrap it with `\\hyperlink{strongs-<num>}{<ESV word>}`. "
            "Guidelines:\n"
            "   - Match by meaning — ESV and NET often translate the same Greek word differently\n"
            "   - Skip function words: articles (a, an, the), basic conjunctions (and, or, but), prepositions (in, of, to)\n"
            "   - Link each Strong's number at most once per verse\n"
            "   - Only link when confident — skip uncertain matches\n"
            "   - The \\hyperlink command must use the exact format: \\hyperlink{strongs-NUM}{word}\n\n"
            f"Strong's number mappings (NET rendering):\n{strongs_list}\n"
        )
    else:
        prompt = SCRIPTURE_ANALYSIS_PROMPT

    request_body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 8192,
        "output_config": {"effort": "low"},
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\nReference: {reference}\n\n{text}"
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_API_VERSION
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_MESSAGES_URL,
                json=request_body,
                headers=headers,
                timeout=120.0
            )
            response.raise_for_status()

        data = response.json()
        content_blocks = data.get("content", [])

        if content_blocks:
            for block in content_blocks:
                if block.get("type") == "text":
                    result = block.get("text", "").strip()
                    if result:
                        if _scripture_content_tokens(result) != _scripture_content_tokens(text):
                            logger.warning("AI changed scripture words or numbers for %s; using original text", reference)
                            return text
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
    # Reapply fixed verse gaps after AI formatting as well as deterministic
    # conversion; the package owns the entire space after each verse number.
    body = re.sub(r"(\\vs\{\d+\})\s+", r"\1", body)

    # Native scripture headings are forbidden inside its poetry environment.
    # Balance braces so nested formatting, multiline headings and following
    # same-line verse commands retain their exact content and poetry membership.
    def split_poetry_headings(match: Match[str]) -> str:
        content = match.group(1)
        parts = []
        cursor = 0
        for heading in re.finditer(r"\\heading\s*\{", content):
            if heading.start() < cursor:
                continue
            depth = 1
            end = None
            for token in re.finditer(r"\\.|[{}]", content[heading.end():], re.DOTALL):
                if token.group() == "{":
                    depth += 1
                elif token.group() == "}":
                    depth -= 1
                if depth == 0:
                    end = heading.end() + token.end()
                    break
            if end is None:
                return match.group(0)
            parts.extend([(False, content[cursor:heading.start()]), (True, content[heading.start():end])])
            cursor = end
        if not parts:
            return match.group(0)
        parts.append((False, content[cursor:]))
        return "\n".join(
            part.strip() if is_heading else
            "\\begin{poetry}\n" + part.strip() + "\n\\end{poetry}"
            for is_heading, part in parts if part.strip()
        )

    body = re.sub(r"\\begin\{poetry\}(.*?)\\end\{poetry\}", split_poetry_headings, body, flags=re.DOTALL)

    # A drop chapter must be in the same environment as its opening lines.
    # Before poetry it becomes a detached number above the verse instead.
    body = re.sub(r"(\\ch\{\d+\})\s*\\begin\{poetry\}", r"\\begin{poetry}\n\1", body)

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
                spec.options.include_headings,
            )

            # If strongs_overlay, fetch NET to build word→Strong's map for AI annotation
            strongs_word_map = None
            if spec.strongs_overlay and not spec.nolinks:
                try:
                    net_result = await fetch_scripture(
                        spec.reference, ScriptureVersion.NET, ScriptureLookupOptions()
                    )
                    strongs_word_map = _extract_strongs_word_map(net_result.text)
                    logger.info("Built Strong's word map with %d entries for %s", len(strongs_word_map), spec.reference)
                except Exception as exc:
                    logger.warning("Failed to fetch NET for strongs_overlay on %s: %s", spec.reference, exc)

            # Apply AI analysis to detect poetry, tag divine names, and optionally add Strong's links
            analyzed = await _analyze_scripture_with_ai(
                formatted,
                result.canonical or result.reference,
                strongs_word_map=strongs_word_map,
            )
            # Re-apply smart-quote conversion after AI (Claude may normalize Unicode quotes)
            analyzed = _smart_scripture_quotes(analyzed)
            rendered = _render_scripture(result.canonical or result.reference, spec.version, analyzed)
            replacements[spec.raw] = rendered
            # Collect reference for commentary appendix
            _collected_references.add(result.canonical or spec.reference)
        except ScriptureLookupError as exc:
            logger.warning("Skipping scripture placeholder — lookup failed: %s (%s): %s",
                           spec.reference, spec.version.value, exc)
            replacements[spec.raw] = f"% [scripture not found: {spec.reference}]"
        except Exception as exc:
            logger.exception("Unexpected error while fetching scripture for %s", spec.reference)
            replacements[spec.raw] = f"% [scripture error: {spec.reference}]"

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
