#!/usr/bin/env python3
"""
Prepare lsj-js dictionary.json → app/lsj.json

Usage:
    python scripts/prepare_lsj_json.py /path/to/dictionary.json

Download dictionary.json from:
    https://raw.githubusercontent.com/perseids-project/lsj-js/master/src/dictionaries/dictionary.json

The input is keyed by Greek lemma → HTML definition string.
Output JSON structure:
    {"3056": {"lemma": "λόγος", "entry": "plain-text definition..."}, ...}
"""
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

APP_DIR = Path(__file__).parent.parent / "app"
STRONGS_PATH = APP_DIR / "strongs_greek.json"

# Strip HTML tags
_TAG_RE = re.compile(r'<[^>]+>')
# Truncate at a reasonable length to keep lsj.json manageable
MAX_ENTRY_LEN = 600


def _clean(html_text: str) -> str:
    text = _TAG_RE.sub('', html_text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > MAX_ENTRY_LEN:
        # Truncate at last sentence boundary before the limit
        cut = text[:MAX_ENTRY_LEN].rfind('.')
        text = text[:cut + 1] if cut > MAX_ENTRY_LEN // 2 else text[:MAX_ENTRY_LEN]
    return text


def _nfd(s: str) -> str:
    """Normalize to NFD so OXIA (polytonic) and TONOS (monotonic) compare equal."""
    return unicodedata.normalize("NFD", s)


def _build_strongs_map() -> dict[str, str]:
    """Build {nfd_greek_lemma → strongs_num} from strongs_greek.json (NT only)."""
    data = json.loads(STRONGS_PATH.read_text(encoding="utf-8"))
    return {_nfd(v["greek"]): k for k, v in data.items() if int(k) <= 5624}


def main(json_path: str) -> None:
    strongs_map = _build_strongs_map()
    print(f"Strong's map: {len(strongs_map)} NT lemmas")

    lsj_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    print(f"LSJ entries: {len(lsj_data)}")

    out: dict = {}
    for lemma_key, html in lsj_data.items():
        # Normalize: take first word of multi-word keys (e.g. "Α α" → "Α")
        # and strip disambiguating suffixes like " (2)"
        first_word = _nfd(lemma_key.split()[0].rstrip('-'))
        candidate = _nfd(re.sub(r'\s*\(\d+\)\s*$', '', lemma_key).strip())

        # Try exact match first, then first-word match (using NFD for accent normalization)
        num = strongs_map.get(candidate) or strongs_map.get(first_word)
        if not num or num in out:
            continue

        entry_text = _clean(html)
        if not entry_text:
            continue

        out[num] = {"lemma": candidate, "entry": entry_text}

    out_path = APP_DIR / "lsj.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    total = len(out)
    coverage = total / len(strongs_map) * 100
    print(f"Wrote {total} entries ({coverage:.0f}% of NT lemmas) → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <dictionary.json>")
        sys.exit(1)
    main(sys.argv[1])
