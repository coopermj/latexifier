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
