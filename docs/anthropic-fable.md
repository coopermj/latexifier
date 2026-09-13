# Anthropic Fable migration

Updated 2026-09-13. All six Anthropic request sites use `claude-fable-5-1`
through `ANTHROPIC_MODEL` in `app/anthropic_config.py`: PDF extraction, text
extraction, reference normalization, missing-reference assignment, scripture
formatting, and optional sermon-slide analysis. The Anthropic endpoint and existing API key are unchanged.
See [sermon-slides.md](sermon-slides.md) for the slide workflow and its additional validation.

Fable 5.1's always-on adaptive thinking can precede the text response. Both
reference helpers now collect text blocks instead of assuming the first block
contains JSON. The other consumers already select text blocks.

Extraction uses medium effort, an 8,192-token output budget and a 120-second
HTTP timeout. Scripture formatting uses low effort with the same budget and
HTTP timeout. Reference helpers use low effort, 4,096 tokens and 60 seconds.
These budgets allow room for thinking as well as returned JSON or LaTeX.
No disabled/manual thinking parameters, forced tools, or assistant prefill are
sent. The existing scripture word-preservation and quote fixes remain active.

Official references:
- https://platform.claude.com/docs/en/models/fable-5-1/overview
- https://platform.claude.com/docs/en/models/fable-5-1/migration-guide

The account's live Models API confirmed access to `claude-fable-5-1`.
Regression verification: 73 tests passed, with three existing deprecation
warnings, plus JavaScript syntax, Python compileall and `git diff --check`.
Mocked tests cover all five request sites with thinking before returned text.
Live validation results for the supplied sermon are stored locally under
`data/fable-validation/` (ignored by Git); routine tests make no paid API calls.

Five live Messages API requests returned HTTP 200 with response model
`claude-fable-5-1` and `stop_reason=end_turn`. The sermon title, author, passage,
four sections and eight subpoints were verified; live normalization, assignment
and scripture-formatting checks also passed. PDF-input extraction was covered
by the mocked regression, not a live PDF upload.
