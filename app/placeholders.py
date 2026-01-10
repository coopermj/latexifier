import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Match

from .scripture import (
    ScriptureLookupError,
    ScriptureLookupOptions,
    ScriptureVersion,
    fetch_scripture,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r"\[\[scripture:([^\]]+)\]\]", re.IGNORECASE)


class ScripturePlaceholderError(Exception):
    """Raised when a scripture placeholder cannot be processed."""


@dataclass
class PlaceholderSpec:
    raw: str
    reference: str
    version: ScriptureVersion
    options: ScriptureLookupOptions


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
) -> str:
    """
    Convert plain text with verse numbers into scripture.sty macros.

    - Adds \\ch{#} for the chapter at the start (best-effort from reference).
    - Converts verse numbers at line starts into \\vs{#}.
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

    verse_pattern = re.compile(r"(^|\n)\s*\[?(\d+)\]?\s+")

    def verse_repl(match: Match[str]) -> str:
        if include_verse_numbers:
            return f"{match.group(1)}\\vs{{{match.group(2)}}} "
        return match.group(1)

    converted = verse_pattern.sub(verse_repl, clean)

    if include_verse_numbers:
        chapter = _extract_chapter(reference)
        if chapter:
            converted = f"\\ch{{{chapter}}} " + converted

    return converted


def _render_scripture(result_ref: str, version: ScriptureVersion, text: str) -> str:
    """
    Wrap fetched text in the scripture environment from the scripture package.
    """
    reference_arg = result_ref.replace("[", "").replace("]", "")
    version_arg = f"[version={version.value}]" if version else ""
    body = text.strip()
    return (
        f"\\begin{{scripture}}[{reference_arg}]{version_arg}\n"
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


async def process_scripture_placeholders(work_dir: Path, main_file: str) -> None:
    """
    Replace scripture placeholders in all .tex files under work_dir.

    Placeholder syntax:
      [[scripture:<reference>|<version>|headings=true|verses=true|footnotes=false|copyright=true]]
    Version defaults to ESV. Options are optional.
    """
    tex_files = list(work_dir.rglob("*.tex"))
    if not tex_files:
        return

    placeholder_specs: dict[str, PlaceholderSpec] = {}
    file_placeholders: dict[Path, set[str]] = {}

    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = tex_file.read_text(errors="replace")

        matches = PLACEHOLDER_PATTERN.findall(content)
        if not matches:
            continue

        file_placeholders[tex_file] = set(matches)
        for raw in matches:
            raw_key = raw.strip()
            if raw_key not in placeholder_specs:
                placeholder_specs[raw_key] = _parse_spec(raw_key)

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
            )
            rendered = _render_scripture(result.canonical or result.reference, spec.version, formatted)
            replacements[spec.raw] = rendered
        except ScriptureLookupError as exc:
            errors.append(f"{spec.reference} ({spec.version.value}): {exc}")
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected error while fetching scripture for %s", spec.reference)
            errors.append(f"{spec.reference} ({spec.version.value}): {exc}")

    if errors:
        raise ScripturePlaceholderError(
            "Failed to fetch scripture for: " + "; ".join(errors)
        )

    for tex_file, specs in file_placeholders.items():
        try:
            content = tex_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = tex_file.read_text(errors="replace")

        for raw in specs:
            placeholder = f"[[scripture:{raw}]]"
            replacement = replacements.get(raw)
            if not replacement:
                continue
            content = content.replace(placeholder, replacement)

        tex_file.write_text(content, encoding="utf-8")

    # Ensure the scripture package is available in the main TeX file
    main_path = work_dir / main_file
    if main_path.exists():
        _ensure_scripture_package(main_path)
    else:
        logger.warning("Main TeX file %s not found when ensuring scripture package", main_file)
