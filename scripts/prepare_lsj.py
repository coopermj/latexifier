#!/usr/bin/env python3
"""
Prepare Perseus LSJ XML → app/lsj.json

Usage:
    python scripts/prepare_lsj.py /path/to/lsj.xml [/path/to/lsj2.xml ...]

Matches LSJ headwords against strongs_greek.json Greek fields to key
output entries by Strong's number.

Output JSON structure:
    {"3056": {"lemma": "λόγος", "entry": "I. ... II. ..."}, ...}

Prerequisites — download LSJ XML:
    git clone --no-checkout --filter=blob:none \\
      https://github.com/PerseusDL/canonical-greekLit.git /tmp/canonical-greekLit
    cd /tmp/canonical-greekLit
    git sparse-checkout set data/tlg0448/tlg001
    git checkout
    # Then run:
    python scripts/prepare_lsj.py /tmp/canonical-greekLit/data/tlg0448/tlg001/*.xml
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APP_DIR = Path(__file__).parent.parent / "app"
STRONGS_PATH = APP_DIR / "strongs_greek.json"


def _build_strongs_map() -> dict[str, str]:
    """Build {greek_lemma → strongs_num} from strongs_greek.json."""
    data = json.loads(STRONGS_PATH.read_text(encoding="utf-8"))
    # Only NT numbers (1-5624 are Greek; 8674+ are Hebrew)
    return {v["greek"]: k for k, v in data.items() if int(k) <= 5624}


def _extract_text(element) -> str:
    """Recursively extract all text content from an XML element."""
    parts = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        child_text = _extract_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _clean_entry(raw: str) -> str:
    """Collapse whitespace and clean up LSJ entry text."""
    text = re.sub(r'\s+', ' ', raw).strip()
    # Remove XML artifacts that slipped through
    text = re.sub(r'<[^>]+>', '', text)
    return text


def process_file(xml_path: str, strongs_map: dict, out: dict) -> int:
    matched = 0
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"  XML parse error in {xml_path}: {e} — skipping")
        return 0

    root = tree.getroot()

    # Find all entry elements — LSJ uses div2 with type="main" or entryFree
    entries = (
        root.findall(".//{*}div2[@type='main']")
        or root.findall(".//{*}entryFree")
        or root.findall(".//{*}entry")
    )

    for entry in entries:
        # Get headword: try <head> child, then 'key' attribute, then 'n' attribute
        head_el = entry.find("{*}head") or entry.find("head")
        if head_el is not None:
            headword_raw = (head_el.text or "").strip()
        else:
            headword_raw = entry.get("key", entry.get("n", "")).strip()

        if not headword_raw:
            continue

        # Take only the first word (drop ", ου, ὁ" grammatical info)
        headword = headword_raw.split(",")[0].strip()

        strongs_num = strongs_map.get(headword)
        if not strongs_num:
            continue  # Not a Greek NT word we know

        if strongs_num in out:
            continue  # Already matched (first match wins)

        # Extract sense/definition text
        senses = entry.findall(".//{*}sense") or entry.findall(".//sense")
        if senses:
            entry_text = " ".join(
                f"{s.get('n', '')}. {_clean_entry(_extract_text(s))}".strip()
                for s in senses
                if _extract_text(s).strip()
            )
        else:
            entry_text = _clean_entry(_extract_text(entry))

        if not entry_text.strip():
            continue

        out[strongs_num] = {"lemma": headword, "entry": entry_text}
        matched += 1

    return matched


def main(xml_paths: list[str]) -> None:
    strongs_map = _build_strongs_map()
    print(f"Strong's map: {len(strongs_map)} NT lemmas")

    out: dict = {}
    for path in xml_paths:
        print(f"Processing {path}…")
        n = process_file(path, strongs_map, out)
        print(f"  → {n} entries matched")

    out_path = APP_DIR / "lsj.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=None), encoding="utf-8")

    total = len(out)
    coverage = total / len(strongs_map) * 100
    print(f"\nWrote {total} entries ({coverage:.0f}% of NT lemmas) → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <lsj.xml> [<lsj2.xml> ...]")
        sys.exit(1)
    main(sys.argv[1:])
