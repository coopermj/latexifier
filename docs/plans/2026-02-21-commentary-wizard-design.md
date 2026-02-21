# Design: Commentary Review Wizard

**Date:** 2026-02-21
**Status:** In progress — Section 1 (API & Data Model) approved

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

## Section 2: Wizard UI (pending approval)

_To be designed._

### Wizard steps

1. **Input** — Notes text, cover image, bulletin/prayer PDFs, commentary source checkboxes. Button: "Extract Outline"
2. **Review** — Shows extracted outline summary + commentary candidate cards per scripture reference. User checks/unchecks individual entries. Button: "Generate PDF"
3. **Result** — Download PDF / TeX links (same as today)

### Commentary candidate card (per reference)

Each scripture reference found in the outline gets a card grouping entries by source:

```
James 3:1–5
├── Matthew Henry
│   [x] v.1–4  "The tongue is a fire, a world of iniquity..."
│   [ ] v.5–6  "Behold, how great a matter a little fire kindleth..."
└── Calvin's Commentary
    [x] v.1–2  "By the word teachers he means those who preside..."
```

---

## Open Questions

- Should Step 2 also allow the user to edit the extracted outline (title, points) before compiling?
- Should commentary candidates include a truncated preview (~200 chars) or the full text?
- How should references with no available commentary be shown (hidden vs. greyed out)?
