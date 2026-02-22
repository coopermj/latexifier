# Design: Commentary Review Wizard

**Date:** 2026-02-21
**Status:** Approved — all sections reviewed

## Problem

The current web UI is a single-step form: paste notes, check commentary sources, click "Generate PDF." Commentary is auto-selected from the database with no user visibility or control over which excerpts appear in the document.

## Goal

Add a multi-step wizard that lets users review the extracted sermon outline and select specific commentary excerpts — per verse/point, per source — before compiling the PDF.

## Approach

**Client-side state wizard (Approach A).** Split the current single call into two API calls; all intermediate state lives in the browser (no server-side persistence). The sermon payload (~50–100KB) is small enough that round-tripping it is not a concern.

---

## Section 1: API & Data Model (approved)

### New endpoint: `POST /web/extract`

**Request** (same fields as today's generate minus compile-only options):
```json
{
  "notes": "...",
  "image": "base64...",
  "commentaries": ["mhc", "calvincommentaries", "scofield"]
}
```

**Response:**
```json
{
  "outline": { ...SermonOutline... },
  "candidates": {
    "James 3:1-5": {
      "mhc": [
        { "verse_start": 1, "verse_end": 4, "text": "The tongue is a fire..." },
        { "verse_start": 5, "verse_end": 6, "text": "..." }
      ],
      "calvincommentaries": [
        { "verse_start": 1, "verse_end": 2, "text": "By the word teachers..." }
      ]
    }
  }
}
```

### Modified: `POST /web/generate`

Two new optional fields added (existing API stays backward-compatible):

| Field | Type | Description |
|---|---|---|
| `outline` | `SermonOutline \| null` | Pre-extracted outline. If present, skip Claude re-extraction. |
| `commentary_selections` | `{ref: [{source, entry_index}]}` | Specific entries to include. If present, bypasses auto-fetch. |

### `sermon_latex.py` change

`generate_sermon_latex()` gets a new optional parameter:

```python
commentary_overrides: dict[str, list[CommentaryEntry]] | None = None
```

If provided, these entries are used directly for matching references instead of querying the DB. This is the only internal change needed to support pre-selected commentary.

---

## Section 2: Wizard UI (approved)

### Step indicator

Simple 1–2–3 indicator at top of page showing current step.

### Step 1 — Input

Same fields as today's form. Button relabeled "Extract Outline →". Spinner shows "Extracting…" while Claude runs + commentaries are fetched.

### Step 2 — Review

- Extracted metadata shown read-only at top (title, speaker, date, main scripture)
- One card per scripture reference found in the outline, labeled with the point it belongs to
- Within each card, entries grouped by source, each with a checkbox
- First entry per source per reference is **checked by default**
- Commentary text truncated to ~150 chars with "show more ▾" toggle
- References with no commentary from selected sources are hidden
- "← Back" returns to Step 1; "Generate PDF →" compiles with selections
- Outline fields (title, speaker, points) are read-only — editing extracted metadata is out of scope

### Step 3 — Done

Download PDF and TeX links. "← Start over" resets to Step 1.

### Commentary card layout (per reference)

```
┌── James 3:1–5 (Point 1) ──────────────────────────────┐
│  Matthew Henry                                         │
│  ☑ v.1–4  "The tongue is a fire, a world of iniquity… │
│            [show more ▾]                               │
│  ☐ v.5–6  "Behold, how great a matter a little fire…  │
│                                                        │
│  Calvin's Commentaries                                 │
│  ☑ v.1–2  "By the word teachers he means those who…   │
└────────────────────────────────────────────────────────┘
```
