# Greek Interlinear Branch — Design Spec

**Date:** 2026-04-05
**Branch:** `greek`
**Status:** Approved

---

## Goal

Replace the ESV main-passage section with a side-by-side interlinear layout: Greek word-stacked interlinear on the left (50%), clean ESV on the right (50%). English glosses in the interlinear are hyperlinked to a rich Lexicon appendix containing the Strong's definition and full Liddell-Scott-Jones entry for each word. OT passages fall back to the current ESV-only layout.

---

## What Changes vs. `main`

- **Removed:** `strongs_overlay` on the main passage ESV (the AI-assisted word annotation approach from v1.0.0)
- **Removed:** Greek Word Study appendix (`_render_word_study_from_strongs`) — superseded by the Lexicon
- **Added:** Interlinear spread (paracol, 50/50)
- **Added:** Lexicon section (after Commentary, before Bulletin/Prayer)
- **Added:** NT detection logic
- **Updated:** Table of Contents to reference all sections

Everything else (sermon points, commentary wizard, bulletin/prayer injections) is unchanged.

---

## Data Sources

### Berean Interlinear Bible (`data/berean_nt.json`)

Source: Berean Interlinear Bible, freely downloadable TSV from berean.bible.

Fields used per word: inflected Greek form, lemma, Strong's number (e.g. `G3056`), morphology code, English gloss.

Pre-processed structure:
```json
{
  "John": {
    "1": {
      "1": [
        {"greek": "Ἐν", "lemma": "ἐν", "strongs": "1722", "gloss": "In", "morph": "PREP"},
        {"greek": "ἀρχῇ", "lemma": "ἀρχή", "strongs": "746", "gloss": "beginning", "morph": "N-DSF"}
      ]
    }
  }
}
```

Preparation script: `scripts/prepare_berean.py` — reads Berean TSV, writes `data/berean_nt.json`.

### Liddell-Scott-Jones Dictionary (`app/lsj.json`)

Source: Perseus Digital Library LSJ XML (public domain, available on GitHub at PerseusDL/canonical-greekLit).

Keyed by Strong's number (mapped via lemma from Berean data). Structure:
```json
{
  "3056": {
    "lemma": "λόγος",
    "entry": "I. the word by which the inward thought is expressed. II. a saying, proverb, maxim. III. reason, ground, account. IV. in NT writers, the divine Word."
  }
}
```

Preparation script: `scripts/prepare_lsj.py` — parses Perseus LSJ XML, maps lemmas to Strong's numbers using Berean data, writes `app/lsj.json`.

---

## New Application Modules

### `app/interlinear.py`

```python
def is_nt_passage(reference: str) -> bool
    """Return True if reference is a New Testament book."""

def get_passage_words(reference: str) -> list[dict] | None:
    """
    Return word list for a parsed NT reference, or None if OT/unknown.
    Each dict: {greek, lemma, strongs, gloss, morph, verse}.
    """
```

Loads `data/berean_nt.json` at import (cached). Parses the reference (book, chapter, verse range) and returns all words in order with their verse number attached for verse-boundary rendering.

### `app/lsj.py`

```python
def get_lsj_entry(strongs_num: str) -> str | None:
    """Return LSJ entry text for a Strong's number, or None."""
```

Loads `app/lsj.json` at import (cached).

---

## Document Layout

### Table of Contents (Title Page)

Rendered as the existing manual hyperlink table. Entries shown conditionally:

| Entry | Condition |
|---|---|
| Greek Interlinear | NT passage only |
| Sermon Notes | always |
| Commentary | if commentary sources selected |
| Lexicon | NT passage only |
| Sunday Bulletin | if bulletin PDF uploaded |
| Prayer Requests | if prayer PDF uploaded |

### Page Order

```
Title page (with TOC)
→ Interlinear spread        [NT only; OT → current ESV multicols layout]
→ Sermon notes
→ Commentary appendix       [if selected]
→ Lexicon                   [NT only]
→ Sunday Bulletin           [if uploaded]
→ Prayer Requests           [if uploaded]
```

---

## Interlinear Spread (`_render_interlinear_passage`)

Uses `paracol` with `\columnratio{0.5}`.

### New LaTeX command

Added to the document preamble:

```latex
% Interlinear word unit: Greek above, linked gloss below
\newcommand{\intword}[3]{%  {greek}{gloss}{strongs-num}
  \begin{tabular}[t]{@{}c@{}}
    {\greekfont\small #1}\\[1pt]
    \hyperlink{lex-#3}{\scriptsize\textit{#2}}
  \end{tabular}\hspace{5pt}%
}
```

The `\hyperlink` target uses prefix `lex-` (e.g. `lex-3056`) to avoid collision with any legacy `strongs-` anchors.

### Verse boundary rendering

Each verse group is preceded by a small verse number:

```latex
{\color{gray}\scriptsize 1}~\intword{Ἐν}{In}{1722}\intword{ἀρχῇ}{beginning}{746}...
```

### Full spread block

```latex
\newpage{}
\hypertarget{interlinear}{}
\columnratio{0.5}
\setlength{\columnsep}{1.5em}
\begin{paracol}{2}
  \small
  \raggedright
  % ... \intword calls grouped by verse ...
\switchcolumn
  \raggedright
  [[scripture:John 1:1-3|ESV|nolinks=true]]
\end{paracol}
```

The ESV placeholder uses `nolinks=true` (paracol compatibility, no hyperlinks in right column).

### OT fallback

When `is_nt_passage()` returns False (or Berean data missing for the reference), `generate_sermon_latex` renders the passage identically to `main` branch: `\begin{multicols}{2}` with the ESV placeholder (no strongs_overlay).

---

## Lexicon Section (`_render_lexicon_appendix`)

Placed after Commentary, before Bulletin/Prayer.

### Entry format

For each unique Strong's number appearing in the passage (sorted numerically):

```latex
\hypertarget{lex-3056}{}
\vspace{12pt}
{\greekfont\large λόγος}\quad{\wordstudy\itshape logos}\hfill{\wordstudy\textbf{G3056}}
\hrule\vspace{4pt}
{\wordstudy\small noun, masc. --- \textit{word, reason, speech, account}}\\[4pt]
{\commentaryfont\small
  \textbf{Liddell \& Scott} --- I. the word by which the inward thought is expressed.
  II. a saying, proverb, maxim. III. reason, ground, account.
  IV. \textit{in NT:} the divine Word, Logos.
}
```

Fields shown:
- **Header line:** Greek (large, greekfont), transliteration from `strongs_greek.json` (italic), Strong's number (right-aligned, bold)
- **Definition line:** grammatical form from Berean morph code + Strong's definition (from `strongs_greek.json`)
- **L&S block:** full entry text from `lsj.json` (commentaryfont, small)

If no LSJ entry exists for a word (e.g. proper nouns, particles), only the Strong's header and definition line are rendered — no L&S block.

---

## Data Prep Scripts

Both scripts are one-time setup tools, not part of the runtime.

### `scripts/prepare_berean.py`
- Reads Berean TSV (path as CLI arg)
- Groups rows by Book → Chapter → Verse
- Writes `data/berean_nt.json`
- Prints summary: book count, word count

### `scripts/prepare_lsj.py`
- Reads Perseus LSJ XML file (path as CLI arg)
- Reads `data/berean_nt.json` to build lemma → Strong's number mapping
- For each LSJ entry whose lemma appears in Berean, extracts plain-text entry (strips XML tags, preserves I./II. structure)
- Writes `app/lsj.json` keyed by Strong's number
- Prints coverage: N of M Berean lemmas matched in LSJ

---

## Files Created / Modified

| File | Action |
|---|---|
| `scripts/prepare_berean.py` | New |
| `scripts/prepare_lsj.py` | New |
| `data/berean_nt.json` | New (generated) |
| `app/lsj.json` | New (generated) |
| `app/interlinear.py` | New |
| `app/lsj.py` | New |
| `app/sermon_latex.py` | Modified — interlinear spread, lexicon, updated TOC, removed word study |
| `app/placeholders.py` | Minor — strongs_overlay option kept but unused for main passage |

---

## Out of Scope (this branch)

- OT / Hebrew interlinear (BDB lexicon, RTL typesetting)
- Morphological parsing display (case, tense, mood) in Lexicon entries
- User-editable interlinear in the web wizard
