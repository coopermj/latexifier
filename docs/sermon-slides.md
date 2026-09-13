# Sermon slide additions

The sermon form accepts an optional **Sermon Slides** PDF (10 MB, up to 100 pages, no password protection). Extract Outline sends the PDF and extracted outline to Anthropic Fable through the existing API key. The slide document is treated as source material, not instructions.

Review shows supporting passages and original visual crops with their source slide numbers. Uncheck additions to exclude them, or change **Place with** to another outline section. Unmatched meaningful slides are reported. Repeated outline text, passages already covered by the main passage, and decorative artwork are skipped. With no slides uploaded, the existing workflow is unchanged.

Supporting passages use the existing NET Bible lookup and Scripture typography pipeline. They appear as labeled pullouts beside the matching notes. Images, diagrams and tables are cropped from the source PDF and placed at the start of the matching section, across the page width. Tables preserve the original appearance as images rather than becoming editable table cells. Source crops are rasterized to a maximum dimension of approximately 1,600 pixels.

The review retains the original PDF and analysis in browser memory. Generate sends both back; a SHA-256 check prevents using analysis from a different deck. Targets, references, slide numbers and crop bounds are validated again. Reviewed generation does not repeat the slide-analysis API call. Start Over and logout clear the upload and analysis. Failed analysis or unavailable supporting Scripture produces an error rather than a successful PDF missing requested content.

## API

- `POST /web/extract`: existing fields plus optional `slides_pdf` (base64). Response adds `slide_analysis` and `slide_previews` (PNG base64 by generated asset filename).
- `POST /web/generate`: optional `slides_pdf` plus reviewed `slide_analysis`. If the PDF is supplied without analysis, generation analyzes it. Analysis without its PDF is rejected.
- Analysis contains `pdf_sha256`, `page_count`, `items`, and `unmatched_slides`. Items contain `id`, `kind`, `target`, `label`, `slide`, `enabled`, and either `reference` or normalized `bbox`.
- Targets are `foundation`, `p0` for a point without subpoints, or `p1.s0` for a subpoint. Indices are zero-based; source slide numbers are one-based.

Install the updated `requirements.txt` to obtain PyMuPDF. The API call uses the shared `ANTHROPIC_MODEL` setting (`claude-fable-5-1`), medium effort, a 16,000-token response budget and a 180-second timeout. The full request may also include outline extraction and commentary retrieval, so upstream HTTP timeouts should allow for that work.

## Verification on September 13, 2026

The supplied 30-page **Isaiah 1 Sermon Slides.pdf** was analyzed through the live Anthropic API. It returned the Isaiah ministry timeline on slide 6 and these matches:

| Source slide | Supporting passage | Destination |
| --- | --- | --- |
| 13 | Habakkuk 3:2 | Rebellion — C. Glimpse of Grace |
| 17 | Psalms 51:17 | Repentance — A. Conceal |
| 18 | Isaiah 29:13 | Repentance — A. Conceal |
| 22 | Isaiah 66:2 | Repentance — B. Confess |
| 28 | Isaiah 53:11 | Redemption — B. Stunning Redemption |
| 29 | Titus 2:13–14 | Redemption — B. Stunning Redemption |

The six supporting passages were fetched and formatted through the real Bible/Fable pipeline. The generated 22-page PDF was rendered for visual inspection, and text extraction verified each passage on the corresponding note page. Repeated layout checks replayed those verified Scripture results. The production generation, asset handling, LuaLaTeX compilation, storage and download routes also passed an integration run using that cache. The final compile had no overfull boxes or missing characters.

Automated tests cover invalid/oversize/encrypted PDFs, API errors/truncation, unsafe references and crop bounds, stale analyses, duplicates, exclusion, no-slide compatibility, missing supporting Scripture and real LuaLaTeX image/table/pullout rendering. `tests/browser_slide_review.cjs` uses Playwright against a local development server with fixture API responses to verify upload, review without commentary, reassignment, exclusion, mobile layout, generation payloads, Start Over and invalid uploads. Set `BASE_URL` if needed; `PLAYWRIGHT_CHROMIUM_EXECUTABLE` optionally selects an installed Chromium browser. Routine tests make no paid API calls.

Final verification: 121 Python tests passed; the Playwright browser regression, JavaScript syntax check, Python compilation and `git diff --check` also passed. Eight dependency/framework deprecation warnings remain.

Local live-validation artifacts and the preview are under the ignored `data/sermon-slides-preview/` directory.
