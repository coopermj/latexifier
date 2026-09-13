# Scripture typography port

Source: `~/geneve_1564` at `cf87dfd`; its architecture and typography notes
describe the source design, rather than instructions for this project.

## Implementation plan

- Vendor CTAN scripture v2.5 (2026-08-23), retain upstream source/license,
  and reapply Geneva's vertical verse-mark protection if absent upstream.
- Ship the package and typography assets inside `app/tex` so Docker and all
  three compilation entry points use the same versions, ahead of stored styles.
- Apply EB Garamond, old-style figures, superior verse-number protrusion,
  fixed 0.3em gaps, biblical-name hyphenation, 1em emergency stretch and
  hyphen demerits to scripture. Detect superior figures in the scripture
  font, since sermon body text uses a different family.
- Preserve scripture paragraph boundaries and use scripture's native heading
  command; keep headings before their chapters. Re-normalize verse gaps after
  optional AI analysis. Test NET and ESV forms and cross-chapter passages.
- Use whole scripture-line poetry spacing and readable chapter paragraphs.
  Keep the sermon's page geometry, notes fonts, interlinear tables and title.
  Full-Bible grids, book initials, edition artwork, running heads, and the
  source's patched global widow-control callbacks are not transplanted into
  this mixed-font paracol layout.
- Run unit regressions and real LuaLaTeX builds through all compilation paths;
  inspect a representative rendered PDF and measure line-edge verse protrusion.

## Verification

Completed 2026-09-13:

- `data/.venv/bin/python -m pytest -q`: **59 passed**, three existing
  FastAPI/Starlette deprecation warnings. The suite includes real two-pass
  LuaLaTeX builds through API, web, and web-with-cover compilation paths.
- The real TeX fixture verifies scripture-font superior detection, local
  line-breaking settings, restoration of body settings, and execution of
  heading reservations. No overfull boxes or missing glyphs in that fixture.
- A two-page A/B measurement with Poppler bounding boxes places a wrapped-line
  verse number at x=56.126pt with protrusion on versus 56.693pt with it off:
  **0.567pt leftward protrusion**. Mid-line digits keep normal spacing.
  Paragraph-initial indent boxes can prevent line-edge protrusion, as in the
  source package; this is not a manual negative-space insertion on every verse.
- A near-page-foot heading moves to page 2 with its opening text.
  Latin Modern Roman correctly selects the non-protruding superscript fallback.
- Built and visually inspected all four pages of the actual sermon-template
  preview at `data/typography-preview/sermon-typography-preview.pdf`, covering
  the title, two-column scripture, parallel notes, Acts 27/28 and poetry.
  No overfull boxes or missing characters. Existing geometry and KOMA package
  warnings remain; those template settings are outside this typography port.
- `node --check app/static/app.js`, Python compileall and `git diff --check`
  pass. No external scripture or AI calls were used for these fixtures.

After full access was enabled, LuaLaTeX compiled successfully with its normal
environment: neither `TEXMFCACHE` nor `openout_any` was overridden. The temporary
test-only cache workaround was removed. Application compiler permissions are
unchanged. Previews remain in the existing ignored `data/` directory, chosen
while root-directory writes were restricted.

Asset versions, licenses and regeneration instructions are in
`app/tex/README.md`; hashes are in `app/tex/upstream/SHA256SUMS`.

## Real sermon integration test

On 2026-09-13, tested the user-supplied **Rebels and Their Redeemer** sermon
through `/web/extract`, `/web/generate`, and both download routes. Anthropic
extraction and scripture formatting, ESV retrieval, and NET retrieval returned
successful live responses. The original notes are retained verbatim in
`tests/fixtures/rebels-and-their-redeemer.txt`; the neighboring JSON is a captured
Anthropic outline for deterministic renderer tests, not a hand-authored source.
Routine pytest runs do not call the live providers.

This specimen exposed three defects that are now covered by regressions:

- Section prose disappeared when the section had subpoints. The Repentance
  introduction now appears once, before its first subpoint.
- NET poetry uses implicitly closed HTML paragraphs. Opening paragraph tags
  and line breaks now preserve word boundaries instead of joining words.
- AI formatting omitted a scripture word. Formatting results that change the
  word/number sequence now fall back to the deterministic source text.
  Divine-name casing and Strong's link wrappers remain allowed.

Final output: `data/rebels-test/rebels-and-their-redeemer.pdf` (22 pages), with
processed TeX, captured outline, live scripture cache, and compile logs alongside.
Rebuilds reused captured live results to avoid repeating paid extraction.
All five unique passage/version pairs passed the word/number preservation check.
All pages were visually inspected; there are no overfull boxes or missing glyphs.
PDF font inspection confirms Tim Cochrell uses Josefin Sans. The existing
note-taking layout leaves substantial whitespace and scripture continuation pages.

Final suite: **66 passed**, three existing deprecation warnings. JavaScript
syntax and `git diff --check` pass. The source's Auditorium Bible page-530 note
is retained in the text fixture but has no field in the current outline schema,
so it is absent from the generated title page. Anthropic also grouped the three
unmarked Accusation sentences into bullets; their wording is retained.

## Supplied Josefin Sans and drop chapters

Author update, September 13, 2026: the author now uses the supplied **Snell
Roundhand Regular**, loaded by filename through `latexgen-snell.sty`. Regular
and Bold are copied unchanged from `SnellRoundhand/Variable-PS/` into `app/tex`.
These are static CFF OpenType files despite the source folder name, so no font
conversion is needed. Josefin Sans remains in the other title-block roles.
The current slide-enriched preview embeds Snell Roundhand for Tim Cochrell;
the Josefin author checks described below record the earlier preview.

The user's subsequent instruction supersedes the paragraph chapter design above.
`latexgen-scripture.sty` now uses bold, lining chapter numerals as two-line drop
caps, with no separate "Chapter N" label. The renderer puts opening chapter
commands inside poetry so the number wraps alongside its first lines.

All ten fonts from `josefin/` are copied unchanged into `app/tex` with descriptive
filenames. `latexgen-josefin.sty` explicitly selects these files for Josefin Sans,
including the author, avoiding installed fonts with the same family name.
The OpenType files work directly with LuaLaTeX; no conversion was necessary.

Verification: **67 tests passed**, including three real two-pass LuaLaTeX paths
using all four primary Josefin faces and drop chapters in prose, poetry and an
Acts 27/28 transition. All ten font hashes match the supplied originals.
The rebuilt 22-page sermon is
`data/josefin-dropcaps-preview/rebels-and-their-redeemer.pdf`. PDF inspection
confirms the author uses the bundled Josefin Sans face. No overfull boxes or
missing glyphs were reported. Rebuilds reused the previously verified scripture
cache and made no new paid AI calls.
