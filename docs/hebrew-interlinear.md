# Hebrew interlinear

Sermon PDFs automatically use Hebrew interlinear for an Old Testament main
passage, just as New Testament passages use Greek. The existing main-passage
option controls both. Each Hebrew word has its English study gloss underneath;
click a gloss to jump to that word's Hebrew lexicon entry. The selected English
Bible translation appears beside the interlinear. Aramaic passages are labeled
Aramaic, and mixed passages are labeled Hebrew and Aramaic.

The Hebrew column reads right to left. English glosses and the English Bible
column read left to right. Glosses retain the source's slash-separated prefixes
and suffixes and grammatical markers, so they are study aids rather than a
sentence translation. Links lead to the main word's lexicon entry, not separate
entries for its attached prefixes and suffixes. Verse markers include chapter
numbers. Missing or unsupported passages fall back to the English Bible layout.

The text, glosses and lexicon are bundled under `app/data/hebrew`; see
[data provenance and rebuilding](hebrew-data.md). Runtime lookup is offline and
does not use Anthropic, Codex, or a separately installed Bible package. Existing
Bible-translation lookup and sermon/slide processing continue as before.

## Typography and distribution

`app/tex/latexgen-hebrew.sty` uses the unmodified Ezra SIL 2.51 font with
LuaLaTeX's HarfBuzz renderer. Direction is scoped to Hebrew paragraphs and
individual Hebrew runs in lexicon definitions. English text retains its own
direction. Both API and web compilers copy the bundled TrueType font into their
temporary working directories. Docker's existing `COPY app/ ./app/` includes
the corpus, lexicon, typography package and font.

Font source: <https://software.sil.org/downloads/r/ezra/EzraSIL-2.51.zip>.
Archive SHA-256:
`f16bcb3ec4473ac6a9f138ee0dbde7cc2f835e93a90cbe8649b3f32677760cc1`.
Extracted `EzraSIL2.51/SILEOT.ttf` to `app/tex/SILEOT.ttf`; no conversion or
modification. Copyright and license are bundled in `app/tex/EzraSIL-LICENSE.txt`.

## Validation

Run `data/.venv/bin/python -m pytest -q`. Corpus tests check English verse
mapping, chapter/range boundaries and Hebrew/Aramaic data. Rendering tests
compile an actual sermon PDF and inspect word positions, embedded font, links,
and English direction. The existing Greek, scripture poetry and slide tests
remain part of the full suite.
