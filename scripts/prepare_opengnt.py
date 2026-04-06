#!/usr/bin/env python3
"""
Prepare OpenGNT CSV → data/berean_nt.json

Usage:
    python scripts/prepare_opengnt.py /path/to/OpenGNT_version3_3.csv

Download OpenGNT_BASE_TEXT.zip from:
    https://github.com/eliranwong/OpenGNT/raw/master/OpenGNT_BASE_TEXT.zip
Then extract: unzip OpenGNT_BASE_TEXT.zip

Output JSON structure (same as prepare_berean.py):
    {BookName: {chapter_str: {verse_str: [{greek, lemma, strongs, gloss, morph}]}}}

Column indices in OpenGNT_version3_3.csv (tab-delimited):
  [6] 〔Book｜Chapter｜Verse〕   — book number (40=Matthew … 66=Revelation)
  [7] 〔OGNTk｜OGNTu｜OGNTa｜lexeme｜rmac｜sn〕
  [10] 〔TBESG｜IT｜LT｜ST｜Español〕  — IT = Berean interlinear gloss
"""
import json
import re
import sys
from pathlib import Path

# OpenGNT book numbers → canonical English names (NT only, 40–66)
BOOK_NAMES = {
    "40": "Matthew", "41": "Mark", "42": "Luke", "43": "John",
    "44": "Acts", "45": "Romans", "46": "1 Corinthians",
    "47": "2 Corinthians", "48": "Galatians", "49": "Ephesians",
    "50": "Philippians", "51": "Colossians", "52": "1 Thessalonians",
    "53": "2 Thessalonians", "54": "1 Timothy", "55": "2 Timothy",
    "56": "Titus", "57": "Philemon", "58": "Hebrews",
    "59": "James", "60": "1 Peter", "61": "2 Peter",
    "62": "1 John", "63": "2 John", "64": "3 John",
    "65": "Jude", "66": "Revelation",
}

# Regex to pull pipe-delimited values out of 〔A｜B｜C〕 groups
_BRACKET_RE = re.compile(r'〔([^〕]*)〕')


def _split(cell: str) -> list[str]:
    """Extract values from a 〔A｜B｜C〕 cell."""
    m = _BRACKET_RE.match(cell.strip())
    if not m:
        return []
    return m.group(1).split("｜")


def main(csv_path: str) -> None:
    out: dict = {}
    total = 0
    skipped = 0

    with open(csv_path, encoding="utf-8") as f:
        next(f)  # skip header row
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 11:
                continue

            bcv = _split(cols[6])   # [Book, Chapter, Verse]
            ref = _split(cols[7])   # [OGNTk, OGNTu, OGNTa, lexeme, rmac, sn]
            trans = _split(cols[10])  # [TBESG, IT, LT, ST, Español]

            if len(bcv) < 3 or len(ref) < 6 or len(trans) < 2:
                skipped += 1
                continue

            book_num = bcv[0].strip()
            book = BOOK_NAMES.get(book_num)
            if not book:
                continue  # OT or unknown

            chapter = bcv[1].strip()
            verse = bcv[2].strip()
            greek = ref[2].strip()    # OGNTa = accented Greek
            lemma = ref[3].strip()    # lexeme
            morph = ref[4].strip()    # rmac
            strongs = ref[5].strip().lstrip("G")  # e.g. G976 → 976
            gloss = trans[1].strip()  # IT = Berean interlinear gloss

            if not greek or not strongs:
                skipped += 1
                continue

            word = {
                "greek": greek,
                "lemma": lemma,
                "strongs": strongs,
                "gloss": gloss,
                "morph": morph,
            }
            out.setdefault(book, {}).setdefault(chapter, {}).setdefault(verse, []).append(word)
            total += 1

    out_path = Path(__file__).parent.parent / "data" / "berean_nt.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    books = len(out)
    print(f"Wrote {total} words across {books} NT books → {out_path}")
    if skipped:
        print(f"Skipped {skipped} malformed rows.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <OpenGNT_version3_3.csv>")
        sys.exit(1)
    main(sys.argv[1])
