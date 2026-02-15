# LaTeXGen TODO

## Current State
LaTeXGen is a web service that converts handwritten/typed sermon notes (via PDF upload or text paste) into beautifully formatted LaTeX/PDF documents with scripture quotations, commentary appendices, and Greek word studies.

### Architecture
- **Backend**: FastAPI (Python), compiled with LuaLaTeX
- **Frontend**: Vanilla HTML/JS served at `/`
- **LLM**: Claude API extracts structured sermon outline from uploaded notes
- **Scripture**: ESV API (main passage), NET Bible API (sub-point scriptures + Strong's numbers)
- **Commentary**: Local SQLite databases (Matthew Henry, Calvin, Scofield)
- **Deployment**: Railway (Docker) for production, `run.sh` for local dev

### Key Files
- `app/main.py` — FastAPI app setup and routes
- `app/llm.py` — Claude API integration for sermon outline extraction
- `app/sermon_latex.py` — LaTeX document generation from parsed outline
- `app/models.py` — Pydantic models (SermonOutline, SermonPoint, Table, etc.)
- `app/scripture.py` — ESV and NET Bible API clients
- `app/commentary.py` — Commentary database queries
- `app/compiler.py` — LuaLaTeX compilation
- `app/routes/web.py` — Web frontend API endpoints
- `app/static/index.html` — Web UI
- `app/static/app.js` — Frontend JavaScript

### Recent Changes (uncommitted)
- Added bulletin PDF and prayer requests PDF upload support (web UI + backend)
- Added Scofield Reference Notes as a commentary source option
- Changed server URL to localhost for local development
- Tables now render inline within points (already committed)

## TODO
- [ ] Restore production server URL in `app/main.py` before deploying (currently set to localhost:8000)
- [ ] Add rate limiting / retry logic for Anthropic API calls in `app/placeholders.py` (currently hits 429s on documents with many scripture refs)
- [ ] Add `.gitignore` entries for generated output files (`sermon_output.tex`, `telling_the_truth.tex`, etc.)
