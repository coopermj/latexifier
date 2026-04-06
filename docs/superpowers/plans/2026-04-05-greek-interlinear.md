# Greek Interlinear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ESV main-passage section with a 50/50 paracol layout — word-stacked Greek/English interlinear on the left, clean ESV on the right — and add a rich Lexicon appendix (Strong's + Liddell-Scott-Jones) linked from every English gloss.

**Architecture:** Two new data modules (`app/interlinear.py`, `app/lsj.py`) load pre-processed JSON files built by one-time prep scripts. `sermon_latex.py` calls them to generate the interlinear paracol block and Lexicon section, replacing the old NET-based word study. OT passages silently fall back to the existing multicol ESV layout.

**Tech Stack:** Python 3.11, LuaLaTeX, `paracol` package (already in preamble), `strongs_greek.json` (already present at `app/strongs_greek.json`), Berean Interlinear Bible TSV, Perseus LSJ XML.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/interlinear.py` | Create | NT detection, Berean data load, passage word lookup |
| `app/lsj.py` | Create | LSJ data load, entry lookup by Strong's number |
| `scripts/prepare_berean.py` | Create | One-time: Berean TSV → `data/berean_nt.json` |
| `scripts/prepare_lsj.py` | Create | One-time: Perseus LSJ XML → `app/lsj.json` |
| `data/berean_nt.json` | Generate | Berean interlinear data (book→ch→verse→words) |
| `app/lsj.json` | Generate | LSJ entries keyed by Strong's number |
| `tests/test_interlinear.py` | Create | Unit tests for `app/interlinear.py` |
| `tests/test_lsj.py` | Create | Unit tests for `app/lsj.py` |
| `app/sermon_latex.py` | Modify | Add `\intword` to preamble, add `_render_interlinear_passage`, `_render_lexicon_appendix`, update `generate_sermon_latex`, remove word study |

---

## Task 1: `app/interlinear.py` — NT detection and passage word lookup

**Files:**
- Create: `app/interlinear.py`
- Create: `tests/test_interlinear.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interlinear.py`:

```python
import pytest
from unittest.mock import patch

SAMPLE_BEREAN = {
    "Ephesians": {
        "4": {
            "22": [
                {"greek": "ἀποθέσθαι", "lemma": "ἀποτίθημι", "strongs": "659", "gloss": "to put off", "morph": "V-AMN"},
                {"greek": "ὑμᾶς", "lemma": "σύ", "strongs": "5209", "gloss": "you", "morph": "P-2AP"},
            ],
            "23": [
                {"greek": "ἀνανεοῦσθαι", "lemma": "ἀνανεόω", "strongs": "365", "gloss": "to be renewed", "morph": "V-PPN"},
            ],
        }
    }
}


def test_is_nt_passage_ephesians():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("Ephesians 4:22-25") is True


def test_is_nt_passage_genesis():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("Genesis 1:1") is False


def test_is_nt_passage_1_corinthians():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("1 Corinthians 13:4") is True


def test_get_passage_words_single_verse():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        words = get_passage_words("Ephesians 4:22")
    assert words is not None
    assert len(words) == 2
    assert words[0]["greek"] == "ἀποθέσθαι"
    assert words[0]["verse"] == 22


def test_get_passage_words_range():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        words = get_passage_words("Ephesians 4:22-23")
    assert words is not None
    assert len(words) == 3
    assert words[2]["verse"] == 23


def test_get_passage_words_ot_returns_none():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        result = get_passage_words("Genesis 1:1")
    assert result is None


def test_get_passage_words_missing_reference_returns_none():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        result = get_passage_words("Ephesians 99:1")
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/micahcooper/latexgen && source .venv/bin/activate
pytest tests/test_interlinear.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.interlinear'`

- [ ] **Step 3: Create `app/interlinear.py`**

```python
"""Berean Interlinear Bible data access — NT only."""
import json
import re
from functools import lru_cache
from pathlib import Path

_NT_BOOKS = {
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
}

# Matches "Book Chapter:Verse" or "Book Chapter:Verse-Verse"
_REF_RE = re.compile(r'^(.+?)\s+(\d+):(\d+)(?:-(\d+))?$')

_BEREAN_PATH = Path(__file__).parent.parent / "data" / "berean_nt.json"


@lru_cache(maxsize=1)
def _load_berean() -> dict:
    if not _BEREAN_PATH.exists():
        return {}
    return json.loads(_BEREAN_PATH.read_text(encoding="utf-8"))


def is_nt_passage(reference: str) -> bool:
    """Return True if the reference names a New Testament book."""
    m = _REF_RE.match(reference.strip())
    if not m:
        return False
    return m.group(1) in _NT_BOOKS


def get_passage_words(reference: str) -> list[dict] | None:
    """
    Return word list for a NT reference, or None for OT/unknown/missing data.

    Each dict has keys: greek, lemma, strongs, gloss, morph, verse (int).
    """
    m = _REF_RE.match(reference.strip())
    if not m:
        return None
    book = m.group(1)
    if book not in _NT_BOOKS:
        return None
    chapter = m.group(2)
    v_start = int(m.group(3))
    v_end = int(m.group(4)) if m.group(4) else v_start

    data = _load_berean()
    ch_data = data.get(book, {}).get(chapter, {})
    if not ch_data:
        return None

    words: list[dict] = []
    for v in range(v_start, v_end + 1):
        for w in ch_data.get(str(v), []):
            words.append({**w, "verse": v})

    return words if words else None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_interlinear.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/interlinear.py tests/test_interlinear.py
git commit -m "feat: add interlinear.py — NT detection and Berean passage word lookup"
```

---

## Task 2: `app/lsj.py` — LSJ entry lookup

**Files:**
- Create: `app/lsj.py`
- Create: `tests/test_lsj.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lsj.py`:

```python
from unittest.mock import patch

SAMPLE_LSJ = {
    "3056": {
        "lemma": "λόγος",
        "entry": "I. the word by which the inward thought is expressed. II. a saying, proverb, maxim."
    },
    "659": {
        "lemma": "ἀποτίθημι",
        "entry": "I. to put away or aside. II. mid., to lay aside for oneself."
    }
}


def test_get_lsj_entry_known():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value=SAMPLE_LSJ):
        result = get_lsj_entry("3056")
    assert result == "I. the word by which the inward thought is expressed. II. a saying, proverb, maxim."


def test_get_lsj_entry_unknown_returns_none():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value=SAMPLE_LSJ):
        result = get_lsj_entry("9999")
    assert result is None


def test_get_lsj_entry_empty_file_returns_none():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value={}):
        result = get_lsj_entry("3056")
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_lsj.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.lsj'`

- [ ] **Step 3: Create `app/lsj.py`**

```python
"""Liddell-Scott-Jones lexicon lookup by Strong's number."""
import json
from functools import lru_cache
from pathlib import Path

_LSJ_PATH = Path(__file__).parent / "lsj.json"


@lru_cache(maxsize=1)
def _load_lsj() -> dict:
    if not _LSJ_PATH.exists():
        return {}
    return json.loads(_LSJ_PATH.read_text(encoding="utf-8"))


def get_lsj_entry(strongs_num: str) -> str | None:
    """Return LSJ entry text for a Strong's number, or None if not found."""
    return _load_lsj().get(strongs_num, {}).get("entry")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_lsj.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/lsj.py tests/test_lsj.py
git commit -m "feat: add lsj.py — LSJ entry lookup by Strong's number"
```

---

## Task 3: `scripts/prepare_berean.py` — Berean TSV → `data/berean_nt.json`

**Files:**
- Create: `scripts/prepare_berean.py`

**Prerequisite:** Download the Berean Interlinear Bible from https://berean.bible/downloads.htm (free). You want the "Interlinear Bible" spreadsheet. Export it to TSV (tab-separated) or use the provided CSV/TSV download. Save it somewhere accessible, e.g. `~/Downloads/berean_nt.tsv`.

- [ ] **Step 1: Inspect the file header**

```bash
head -2 ~/Downloads/berean_nt.tsv | cat -A | head -5
```

Note the column names in the first row. The script below expects these column names (case-sensitive). Adjust the `COL_*` constants if yours differ.

- [ ] **Step 2: Create `scripts/prepare_berean.py`**

```python
#!/usr/bin/env python3
"""
Prepare Berean Interlinear Bible TSV → data/berean_nt.json

Usage:
    python scripts/prepare_berean.py ~/Downloads/berean_nt.tsv

The output JSON has structure:
    {BookName: {chapter_str: {verse_str: [{greek, lemma, strongs, gloss, morph}]}}}
"""
import csv
import json
import sys
from pathlib import Path

# Adjust these if your Berean TSV uses different column names.
# Run:  head -1 your_file.tsv   to see the actual header row.
COL_BOOK    = "Book"          # Full English book name, e.g. "Ephesians"
COL_CHAPTER = "Chapter"       # Integer string, e.g. "4"
COL_VERSE   = "Verse"         # Integer string, e.g. "22"
COL_GREEK   = "Greek"         # Inflected Greek word
COL_LEMMA   = "Lemma"         # Dictionary form (lemma)
COL_STRONGS = "Strongs"       # Strong's number, may include "G" prefix
COL_MORPH   = "Morphology"    # Morphology code, e.g. "V-AMN"
COL_GLOSS   = "English"       # Word-level English gloss

NT_BOOKS = {
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
}


def main(tsv_path: str) -> None:
    out: dict = {}
    skipped = 0
    total = 0

    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        # Validate columns exist
        first_row = next(reader)
        for col in (COL_BOOK, COL_CHAPTER, COL_VERSE, COL_GREEK, COL_LEMMA,
                    COL_STRONGS, COL_MORPH, COL_GLOSS):
            if col not in first_row:
                print(f"ERROR: Column '{col}' not found. Available: {list(first_row.keys())}")
                print("Adjust COL_* constants at the top of this script.")
                sys.exit(1)

        # Process first row then continue
        for row in [first_row] + list(reader):
            book = row[COL_BOOK].strip()
            if book not in NT_BOOKS:
                skipped += 1
                continue

            chapter = row[COL_CHAPTER].strip()
            verse = row[COL_VERSE].strip()
            strongs = row[COL_STRONGS].strip().lstrip("G")  # Normalize to bare number

            word = {
                "greek":   row[COL_GREEK].strip(),
                "lemma":   row[COL_LEMMA].strip(),
                "strongs": strongs,
                "gloss":   row[COL_GLOSS].strip(),
                "morph":   row[COL_MORPH].strip(),
            }

            out.setdefault(book, {}).setdefault(chapter, {}).setdefault(verse, []).append(word)
            total += 1

    out_path = Path(__file__).parent.parent / "data" / "berean_nt.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=None), encoding="utf-8")

    books = len(out)
    print(f"Wrote {total} words across {books} NT books → {out_path}")
    if skipped:
        print(f"Skipped {skipped} non-NT rows.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <berean_nt.tsv>")
        sys.exit(1)
    main(sys.argv[1])
```

- [ ] **Step 3: Run the script**

```bash
cd /Users/micahcooper/latexgen && source .venv/bin/activate
python scripts/prepare_berean.py ~/Downloads/berean_nt.tsv
```

Expected output (numbers will vary):
```
Wrote 138020 words across 27 NT books → .../data/berean_nt.json
```

If you see a column error, check the column names with `head -1 ~/Downloads/berean_nt.tsv` and update the `COL_*` constants.

- [ ] **Step 4: Spot-check the output**

```bash
python3 -c "
import json
d = json.load(open('data/berean_nt.json'))
print(list(d.keys()))
print(d['Ephesians']['4']['22'][:2])
"
```

Expected: list of 27 NT books, then first 2 words of Ephesians 4:22 with `greek`, `lemma`, `strongs`, `gloss`, `morph` keys.

- [ ] **Step 5: Commit**

```bash
git add scripts/prepare_berean.py data/berean_nt.json
git commit -m "feat: add prepare_berean.py and generated berean_nt.json"
```

---

## Task 4: `scripts/prepare_lsj.py` — Perseus LSJ XML → `app/lsj.json`

**Files:**
- Create: `scripts/prepare_lsj.py`

**Prerequisite — download LSJ XML:**

```bash
# Clone only the LSJ file (sparse checkout to avoid downloading the full corpus)
git clone --no-checkout --filter=blob:none \
  https://github.com/PerseusDL/canonical-greekLit.git /tmp/canonical-greekLit
cd /tmp/canonical-greekLit
git sparse-checkout set data/tlg0448/tlg001
git checkout
ls data/tlg0448/tlg001/
```

You'll find one or more XML files (e.g., `tlg0448.tlg001.perseus-grc1.xml`). Note the path to the file(s).

- [ ] **Step 1: Inspect the XML structure**

```bash
head -50 /tmp/canonical-greekLit/data/tlg0448/tlg001/tlg0448.tlg001.perseus-grc1.xml
```

Look for: the element that wraps each entry (`<div2>`, `<entryFree>`, or `<entry>`), the attribute or child element that holds the Greek lemma, and the elements that hold the definition text (`<sense>`, `<def>`, etc.).

- [ ] **Step 2: Create `scripts/prepare_lsj.py`**

```python
#!/usr/bin/env python3
"""
Prepare Perseus LSJ XML → app/lsj.json

Usage:
    python scripts/prepare_lsj.py /path/to/lsj.xml [/path/to/lsj2.xml ...]

Matches LSJ headwords against strongs_greek.json Greek fields to key
output entries by Strong's number.

Output JSON structure:
    {"3056": {"lemma": "λόγος", "entry": "I. ... II. ..."}, ...}
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
```

- [ ] **Step 3: Run the script**

```bash
cd /Users/micahcooper/latexgen && source .venv/bin/activate
python scripts/prepare_lsj.py /tmp/canonical-greekLit/data/tlg0448/tlg001/*.xml
```

Expected output (coverage will vary; 40-70% is normal — proper nouns and particles often don't appear in LSJ):
```
Strong's map: 5624 NT lemmas
Processing ...xml
  → 1847 entries matched
...
Wrote 2300 entries (41% of NT lemmas) → .../app/lsj.json
```

If coverage is 0%, the XML structure differs from expected — print `entry.tag, entry.attrib` inside the loop to debug.

- [ ] **Step 4: Spot-check the output**

```bash
python3 -c "
import json
d = json.load(open('app/lsj.json'))
print('Total entries:', len(d))
print('G3056:', d.get('3056'))
"
```

Expected: entry for λόγος with I./II. structure.

- [ ] **Step 5: Commit**

```bash
git add scripts/prepare_lsj.py app/lsj.json
git commit -m "feat: add prepare_lsj.py and generated lsj.json"
```

---

## Task 5: LaTeX preamble — `\intword` command + `_morph_label` helper

**Files:**
- Modify: `app/sermon_latex.py`

The `\intword{greek}{gloss}{strongs-num}` command renders one interlinear word pair. It uses an inline `tabular` so the Greek and gloss stay centred above each other and flow across the line like text.

- [ ] **Step 1: Write a failing test**

Add to `tests/test_sermon_latex.py`:

```python
def test_preamble_contains_intword():
    """The \intword command must be in the generated preamble."""
    import asyncio
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Genesis 1:1",   # OT → no interlinear, but preamble always emitted
        points=[],
    )
    latex = asyncio.get_event_loop().run_until_complete(
        generate_sermon_latex(outline, include_main_passage=False)
    )
    assert r"\newcommand{\intword}" in latex
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_sermon_latex.py::test_preamble_contains_intword -v
```

Expected: FAIL — `AssertionError`

- [ ] **Step 3: Add `\intword` and `_morph_label` to `sermon_latex.py`**

In `sermon_latex.py`, add the `\intword` command to the preamble string, directly after the `\scripturebullets` definition (around line 222):

```python
# Find this block in the preamble string:
# % Two-column scripture + notes (using paracol for page breaks)
# \newcommand{\scripturebullets}[2]{%
# ...
# }
#
# Add immediately after the closing brace of \scripturebullets:
```

The preamble string (inside the `r"""..."""` block) should gain this section:

```latex
% Interlinear word unit: Greek above, linked English gloss below
\newcommand{\intword}[3]{%
  \begin{tabular}[t]{@{}c@{}}
    {\greekfont\small #1}\\[1pt]
    \hyperlink{lex-#3}{\scriptsize\textit{#2}}%
  \end{tabular}\hspace{5pt}%
}
```

Also add the `_morph_label` Python helper function anywhere near the top of the module (after the imports):

```python
_MORPH_PREFIX = {
    "N": "noun", "V": "verb", "A": "adj.", "ADV": "adv.",
    "PREP": "prep.", "CONJ": "conj.", "ART": "art.", "T": "art.",
    "P": "pron.", "PRT": "part.", "INJ": "interj.",
}

def _morph_label(morph: str) -> str:
    """Convert a Berean morphology code prefix to a readable label."""
    prefix = morph.split("-")[0].upper()
    return _MORPH_PREFIX.get(prefix, morph.lower())
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/test_sermon_latex.py::test_preamble_contains_intword -v
```

Expected: PASS

- [ ] **Step 5: Run all tests to check nothing broke**

```bash
pytest tests/ -v --tb=short
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add app/sermon_latex.py
git commit -m "feat: add \\intword LaTeX command and _morph_label helper to sermon_latex"
```

---

## Task 6: `_render_interlinear_passage()` in `sermon_latex.py`

**Files:**
- Modify: `app/sermon_latex.py`
- Modify: `tests/test_sermon_latex.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sermon_latex.py`:

```python
def test_render_interlinear_passage_structure():
    from app.sermon_latex import _render_interlinear_passage

    words = [
        {"greek": "Ἐν", "lemma": "ἐν", "strongs": "1722", "gloss": "In", "morph": "PREP", "verse": 1},
        {"greek": "ἀρχῇ", "lemma": "ἀρχή", "strongs": "746", "gloss": "beginning", "morph": "N-DSF", "verse": 1},
        {"greek": "ἦν", "lemma": "εἰμί", "strongs": "2258", "gloss": "was", "morph": "V-IAI-3S", "verse": 2},
    ]
    lines = _render_interlinear_passage(words, "John 1:1-2", "ESV")
    combined = "\n".join(lines)

    assert r"\begin{paracol}{2}" in combined
    assert r"\switchcolumn" in combined
    assert r"\hypertarget{interlinear}{}" in combined
    assert r"\intword{Ἐν}{In}{1722}" in combined
    assert r"\intword{ἀρχῇ}{beginning}{746}" in combined
    # Verse boundary markers
    assert r"{\color{gray}\scriptsize 1}" in combined
    assert r"{\color{gray}\scriptsize 2}" in combined
    # ESV placeholder in right column (nolinks=true for paracol)
    assert "[[scripture:John 1:1-2|ESV|nolinks=true]]" in combined
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_sermon_latex.py::test_render_interlinear_passage_structure -v
```

Expected: FAIL — `ImportError` or `AttributeError`

- [ ] **Step 3: Add `_render_interlinear_passage` to `sermon_latex.py`**

Add this function after `_render_table` and before `format_date`:

```python
def _render_interlinear_passage(
    words: list[dict],
    main_passage: str,
    scripture_version: str,
) -> list[str]:
    """
    Render a 50/50 paracol block: interlinear (left) + clean ESV (right).

    words: output of interlinear.get_passage_words() — each has
           greek, lemma, strongs, gloss, morph, verse (int)
    """
    lines = []
    lines.append(r"\newpage{}")
    lines.append(r"\hypertarget{interlinear}{}")
    lines.append(r"\columnratio{0.5}")
    lines.append(r"\setlength{\columnsep}{1.5em}")
    lines.append(r"\begin{paracol}{2}")
    lines.append(r"\small\raggedright")
    lines.append("")

    # Left column: word-stacked interlinear grouped by verse
    current_verse = None
    for w in words:
        if w["verse"] != current_verse:
            if current_verse is not None:
                lines.append("")  # spacing between verses
            current_verse = w["verse"]
            lines.append(rf"{{\color{{gray}}\scriptsize {current_verse}}}~")
        greek = escape_latex(w["greek"])
        gloss = escape_latex(w["gloss"])
        strongs = w["strongs"]
        lines.append(rf"\intword{{{greek}}}{{{gloss}}}{{{strongs}}}")

    lines.append("")
    lines.append(r"\switchcolumn")
    lines.append(r"\raggedright")
    lines.append(scripture_placeholder(main_passage, scripture_version, nolinks=True))
    lines.append("")
    lines.append(r"\end{paracol}")
    lines.append(r"\newpage{}")
    return lines
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/test_sermon_latex.py::test_render_interlinear_passage_structure -v
```

Expected: PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add app/sermon_latex.py tests/test_sermon_latex.py
git commit -m "feat: add _render_interlinear_passage to sermon_latex"
```

---

## Task 7: `_render_lexicon_appendix()` in `sermon_latex.py`

**Files:**
- Modify: `app/sermon_latex.py`
- Modify: `tests/test_sermon_latex.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sermon_latex.py`:

```python
def test_render_lexicon_appendix_entry_structure():
    from unittest.mock import patch
    from app.sermon_latex import _render_lexicon_appendix

    sample_lsj = {"3056": {"lemma": "λόγος", "entry": "I. the word. II. reason."}}
    sample_strongs = {"3056": {"greek": "λόγος", "translit": "lógos", "def": "a word, speech"}}

    with patch("app.sermon_latex.STRONGS_GREEK", sample_strongs), \
         patch("app.sermon_latex.get_lsj_entry", side_effect=lambda n: sample_lsj.get(n, {}).get("entry")):
        lines = _render_lexicon_appendix({"3056"})

    combined = "\n".join(lines)
    assert r"\hypertarget{lex-3056}{}" in combined
    assert "λόγος" in combined
    assert "lógos" in combined
    assert "G3056" in combined
    assert "a word, speech" in combined
    assert "I. the word. II. reason." in combined
    assert r"\section{Lexicon}" in combined


def test_render_lexicon_appendix_no_lsj_still_renders():
    from unittest.mock import patch
    from app.sermon_latex import _render_lexicon_appendix

    sample_strongs = {"1722": {"greek": "ἐν", "translit": "en", "def": "in, by, with"}}

    with patch("app.sermon_latex.STRONGS_GREEK", sample_strongs), \
         patch("app.sermon_latex.get_lsj_entry", return_value=None):
        lines = _render_lexicon_appendix({"1722"})

    combined = "\n".join(lines)
    assert "ἐν" in combined
    assert "in, by, with" in combined
    # No L&S block for words with no LSJ entry
    assert "Liddell" not in combined


def test_render_lexicon_appendix_empty():
    from app.sermon_latex import _render_lexicon_appendix
    lines = _render_lexicon_appendix(set())
    assert lines == []
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_sermon_latex.py::test_render_lexicon_appendix_entry_structure \
       tests/test_sermon_latex.py::test_render_lexicon_appendix_no_lsj_still_renders \
       tests/test_sermon_latex.py::test_render_lexicon_appendix_empty -v
```

Expected: FAIL

- [ ] **Step 3: Add import and module-level constant to `sermon_latex.py`**

At the top of `app/sermon_latex.py`, add the import alongside the existing ones:

```python
from .lsj import get_lsj_entry
```

The existing code already loads `STRONGS_GREEK` at module level as a dict — verify the variable is named `STRONGS_GREEK` (it is, around line 13). The tests patch it by that name.

- [ ] **Step 4: Add `_render_lexicon_appendix` to `sermon_latex.py`**

Add this function after `_render_interlinear_passage`:

```python
def _render_lexicon_appendix(strongs_numbers: set[str]) -> list[str]:
    """
    Render the Lexicon section with one rich entry per unique Strong's number.

    Entry format:
      Greek (large) + transliteration  [right-aligned: G-number]
      grammatical form — Strong's definition
      L&S: <entry text>   (omitted if no LSJ entry exists)
    """
    if not strongs_numbers:
        return []

    lines = []
    lines.append("")
    lines.append(r"\newpage{}")
    lines.append(r"\newgeometry{left=10mm,right=15mm,top=15mm,bottom=10mm}")
    lines.append(r"\hypertarget{lexicon}{}")
    lines.append(r"\section{Lexicon}")
    lines.append(r"\commentaryfont\small")
    lines.append("")

    for num in sorted(strongs_numbers, key=lambda x: int(x)):
        entry = STRONGS_GREEK.get(num)
        if not entry:
            continue

        greek    = entry.get("greek", "")
        translit = entry.get("translit", "")
        defn     = escape_latex(entry.get("def", ""))

        lines.append(rf"\hypertarget{{lex-{num}}}{{}}")
        # Header: Greek (large) + translit, G-number right-aligned
        lines.append(
            rf"{{\greekfont\large {greek}}}\quad"
            rf"{{\wordstudy\itshape {escape_latex(translit)}}}"
            rf"\hfill{{\wordstudy\textbf{{G{num}}}}}"
        )
        lines.append(r"\hrule\vspace{4pt}")
        # Definition line
        lines.append(rf"{{\wordstudy\small \textit{{{defn}}}}}")
        lines.append("")

        # L&S block (optional)
        lsj_text = get_lsj_entry(num)
        if lsj_text:
            lines.append(
                rf"{{\commentaryfont\small \textbf{{Liddell \& Scott}} --- "
                rf"{escape_latex(lsj_text)}}}"
            )
            lines.append("")

        lines.append(r"\medskip")
        lines.append("")

    lines.append(r"\restoregeometry")
    return lines
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
pytest tests/test_sermon_latex.py::test_render_lexicon_appendix_entry_structure \
       tests/test_sermon_latex.py::test_render_lexicon_appendix_no_lsj_still_renders \
       tests/test_sermon_latex.py::test_render_lexicon_appendix_empty -v
```

Expected: all 3 PASS

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add app/sermon_latex.py tests/test_sermon_latex.py
git commit -m "feat: add _render_lexicon_appendix with Strong's and LSJ entries"
```

---

## Task 8: Wire into `generate_sermon_latex()` — TOC, passage, Lexicon, remove word study

**Files:**
- Modify: `app/sermon_latex.py`
- Modify: `tests/test_sermon_latex.py`

This task removes the old NET-based word study, wires up the new interlinear + lexicon, and updates the TOC.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_sermon_latex.py`:

```python
@pytest.mark.asyncio
async def test_generate_sermon_latex_ot_no_interlinear():
    """OT passage → no interlinear hypertarget, no lexicon section."""
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Genesis 1:1",
        points=[],
    )
    with patch("app.sermon_latex.fetch_scripture", side_effect=Exception("no network")):
        latex = await generate_sermon_latex(outline, include_main_passage=True)

    assert r"\hypertarget{interlinear}{}" not in latex
    assert r"\section{Lexicon}" not in latex
    # Fallback to multicols
    assert r"\begin{multicols}{2}" in latex


@pytest.mark.asyncio
async def test_generate_sermon_latex_nt_toc_has_interlinear_and_lexicon():
    """NT passage → TOC contains Greek Interlinear and Lexicon links."""
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata
    from unittest.mock import AsyncMock, patch, MagicMock

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Ephesians 4:22",
        points=[],
    )
    sample_words = [
        {"greek": "ἀποθέσθαι", "lemma": "ἀποτίθημι", "strongs": "659",
         "gloss": "to put off", "morph": "V-AMN", "verse": 22},
    ]
    with patch("app.sermon_latex.get_passage_words", return_value=sample_words), \
         patch("app.sermon_latex.fetch_scripture", side_effect=Exception("no network")):
        latex = await generate_sermon_latex(outline, include_main_passage=True)

    assert r"\hyperlink{interlinear}{Greek Interlinear}" in latex
    assert r"\hyperlink{lexicon}{Lexicon}" in latex
    assert r"\section{Lexicon}" in latex
    assert r"\hypertarget{interlinear}{}" in latex
    assert r"\begin{multicols}{2}" not in latex   # no fallback multicols for NT
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_sermon_latex.py::test_generate_sermon_latex_ot_no_interlinear \
       tests/test_sermon_latex.py::test_generate_sermon_latex_nt_toc_has_interlinear_and_lexicon -v
```

Expected: FAIL

- [ ] **Step 3: Add import to `sermon_latex.py`**

Near the top of `app/sermon_latex.py`, alongside the existing imports, add:

```python
from .interlinear import get_passage_words, is_nt_passage
```

- [ ] **Step 4: Replace the TOC block in `generate_sermon_latex`**

Find the TOC block (around line 338–352 in the original file) and replace it:

```python
    # --- before (remove this) ---
    # lines.append(r"\begin{tabular}{l}")
    # lines.append(r"\hyperlink{sermonnotes}{Sermon Notes} \\[0.3cm]")
    # if include_bulletin:
    #     lines.append(r"\hyperlink{bulletin}{Sunday Bulletin} \\[0.3cm]")
    # if include_prayer_requests:
    #     lines.append(r"\hyperlink{prayer}{Prayer Requests} \\[0.3cm]")
    # lines.append(r"\end{tabular}")
```

Replace with:

```python
    # Determine interlinear eligibility before building TOC
    nt_passage = include_main_passage and main_passage and is_nt_passage(main_passage)
    passage_words = get_passage_words(main_passage) if nt_passage else None
    interlinear_active = nt_passage and passage_words is not None

    lines.append(r"\begin{tabular}{l}")
    if interlinear_active:
        lines.append(r"\hyperlink{interlinear}{Greek Interlinear} \\[0.3cm]")
    lines.append(r"\hyperlink{sermonnotes}{Sermon Notes} \\[0.3cm]")
    if commentary_sources or commentary_overrides is not None:
        lines.append(r"\hyperlink{commentary}{Commentary} \\[0.3cm]")
    if interlinear_active:
        lines.append(r"\hyperlink{lexicon}{Lexicon} \\[0.3cm]")
    if include_bulletin:
        lines.append(r"\hyperlink{bulletin}{Sunday Bulletin} \\[0.3cm]")
    if include_prayer_requests:
        lines.append(r"\hyperlink{prayer}{Prayer Requests} \\[0.3cm]")
    lines.append(r"\end{tabular}")
```

- [ ] **Step 5: Replace the main passage rendering block**

Find the main passage block (around line 358–365 in the original):

```python
    # --- remove this ---
    # Main passage in two columns (with Strong's overlay …)
    if include_main_passage and main_passage:
        lines.append(r"\begin{multicols}{2}")
        lines.append(scripture_placeholder(main_passage, scripture_version, strongs_overlay=True))
        lines.append(r"\end{multicols}")
        lines.append("")
        lines.append(r"\newpage{}")
        lines.append("")
```

Replace with:

```python
    # Main passage: interlinear (NT) or multicols ESV (OT/fallback)
    if include_main_passage and main_passage:
        if interlinear_active:
            lines.extend(_render_interlinear_passage(passage_words, main_passage, scripture_version))
        else:
            lines.append(r"\begin{multicols}{2}")
            lines.append(scripture_placeholder(main_passage, scripture_version))
            lines.append(r"\end{multicols}")
            lines.append("")
            lines.append(r"\newpage{}")
            lines.append("")
```

- [ ] **Step 6: Remove the old NET word study block and add Commentary hypertarget**

Find the word study block (after the sermon points loop):

```python
    # --- remove this entire block ---
    # Greek Word Study appendix - fetch Strong's numbers from NET Bible
    strongs_numbers = set()
    if main_passage:
        try:
            net_result = await fetch_scripture(
                main_passage,
                ScriptureVersion.NET,
                ScriptureLookupOptions()
            )
            strongs_numbers = net_result.strongs_numbers
            logger.info(...)
        except Exception as e:
            logger.warning(...)

    if strongs_numbers:
        lines.extend(_render_word_study_from_strongs(strongs_numbers))
```

Delete it entirely. Then find the commentary appendix call and add a hypertarget before it:

```python
    # Commentary appendix
    if commentary_sources or commentary_overrides is not None:
        lines.append(r"\hypertarget{commentary}{}")   # ← add this line
        commentary_lines = await _render_commentary_appendix(
            main_passage,
            commentary_sources or [],
            preloaded=commentary_overrides,
        )
        lines.extend(commentary_lines)
```

- [ ] **Step 7: Add Lexicon section after Commentary, before Bulletin**

Immediately after the commentary block and before the bulletin block, add:

```python
    # Lexicon appendix (NT passages only)
    if interlinear_active and passage_words:
        strongs_in_passage = {w["strongs"] for w in passage_words if w.get("strongs")}
        lines.extend(_render_lexicon_appendix(strongs_in_passage))
```

- [ ] **Step 8: Run the new tests**

```bash
pytest tests/test_sermon_latex.py::test_generate_sermon_latex_ot_no_interlinear \
       tests/test_sermon_latex.py::test_generate_sermon_latex_nt_toc_has_interlinear_and_lexicon -v
```

Expected: both PASS

- [ ] **Step 9: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass. If `test_render_commentary_appendix_*` tests fail due to the new hypertarget line, verify the commentary block structure matches what those tests expect.

- [ ] **Step 10: Commit**

```bash
git add app/sermon_latex.py tests/test_sermon_latex.py
git commit -m "feat: wire interlinear + lexicon into generate_sermon_latex, update TOC, remove word study"
```

- [ ] **Step 11: Push the greek branch**

```bash
git push -u origin greek
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Left 50%: word-stacked interlinear | Task 6 (`_render_interlinear_passage`) |
| Right 50%: clean ESV, no hyperlinks | Task 6 (`nolinks=true` placeholder) |
| English glosses hyperlinked to Lexicon | Task 5 (`\intword` with `\hyperlink{lex-NUM}`) |
| Lexicon after Commentary, before Bulletin | Task 8 (ordering) |
| Rich entry: Greek header + Strong's + L&S | Task 7 (`_render_lexicon_appendix`) |
| No L&S block for missing entries | Task 7 (guarded by `if lsj_text`) |
| OT fallback to multicols ESV | Task 8 (`interlinear_active` guard) |
| NT detection | Task 1 (`is_nt_passage`) |
| Berean data pipeline | Task 3 (`prepare_berean.py`) |
| LSJ data pipeline | Task 4 (`prepare_lsj.py`) |
| TOC: Interlinear, Sermon Notes, Commentary, Lexicon, Bulletin, Prayer | Task 8 (TOC block) |
| Remove strongs_overlay from main passage | Task 8 (plain placeholder for OT fallback, no overlay anywhere) |
| Remove old word study appendix | Task 8 |
| `lex-` prefix avoids collision with old `strongs-` anchors | Task 5 (`\intword` definition), Task 7 (`\hypertarget{lex-NUM}`) |

**No placeholders:** All steps contain complete code. ✓

**Type consistency:**
- `get_passage_words` → `list[dict] | None` — used as `passage_words` throughout Tasks 6, 7, 8. ✓
- `_render_interlinear_passage(words, main_passage, scripture_version)` — called in Task 8 with same signature. ✓
- `_render_lexicon_appendix(strongs_numbers: set[str])` — called in Task 8 with `{w["strongs"] for w in passage_words}`. ✓
- `STRONGS_GREEK` module-level dict — patched by name in Task 7 tests. ✓
- `get_lsj_entry(strongs_num: str) -> str | None` — called in `_render_lexicon_appendix`. ✓
