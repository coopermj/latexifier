# Sermon Slide Enrichment Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for bounded implementation and independent review. Preserve the existing uncommitted typography and Fable changes. Do not commit or publish unrelated files.

**Goal:** Optionally enrich generated sermon notes from a slide PDF using Anthropic.

**Architecture:** A separate slide module validates PDFs, calls Fable, validates structured matches and renders source crops. Web routes pass reviewed matches to the existing LaTeX renderer and supply cropped assets to compilation. The browser adds upload, review, exclusion and reassignment controls.

**Tech Stack:** FastAPI/Pydantic, httpx, PyMuPDF, vanilla JavaScript, LuaLaTeX.

- [x] Implement typed analysis, PDF limits, Fable matching, source crop extraction and focused tests in `app/slides.py`.
- [x] Integrate extraction/generation routes and matching-page pullout rendering with route/render tests.
- [x] Add optional upload and editable match review with reset and state handling.
- [x] Analyze the supplied deck using the live Fable API; compile and visually inspect actual enrichment and image/table fixtures.
- [x] Run full tests, browser verification and independent review; fix findings and document usage.
