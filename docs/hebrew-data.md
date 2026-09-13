# Offline Hebrew and Aramaic interlinear

`app/hebrew_interlinear.py` provides Hebrew/Aramaic support for all 39 Protestant
Old Testament books: **305,486 word tokens** and **13,087 lexicon entries**.
Runtime does not download anything. The corpus is under `app/data/hebrew` so
Docker's existing `COPY app ...` bundles it with the application.

## Sources and text policy

[STEPBible Data](https://github.com/STEPBible/STEPBible-Data), pinned at
`ae39711d7843b2902d54993e432de9c12d6a4b9a`, provides the four TAHOT files
(`Gen-Deu`, `Jos-Est`, `Job-Sng`, `Isa-Mal`) and TBESH. Attribution and the full
CC BY 4.0 license are bundled in the corpus directory.

The text follows TAHOT's principal Leningrad/Qere rows, including its 27
restored-word rows for text missing from Leningrad. Ketiv and other variant
columns are not emitted. The 14 empty Qere rows represent words not read and
are omitted. The 152 `X` rows are modern Hebrew reconstructions of LXX
additions; they are omitted to avoid presenting reconstructed words as
manuscript Hebrew. This is therefore a specified adaptation of TAHOT, not a
diplomatic manuscript transcription or an apparatus of textual variants.

The **leading English reference** in each row determines chapter and verse.
TAHOT defines this as NRSV English versification. Parenthesized Hebrew
references do not change lookup: e.g., Malachi 4:6 is Hebrew 3:24 and Psalms
3:1 is Hebrew 3:2. Psalm superscriptions are retained at English verse 0;
whole-chapter requests include them, and explicit verse requests include only
the requested verses. An intermediate Psalm in a cross-chapter range begins
at verse 1, consistent with an ordinary numbered-verse range.

Biblical Aramaic is supported word by word through the source morphology
prefix (`A` vs `H`), including the change of language within Daniel 2:4.

## API

`get_hebrew_passage_words(reference)` accepts canonical names, source book
abbreviations, and common Psalm/Song aliases, case-insensitively. Examples:
`Genesis 1:1`, `Gen. 1:1-3`, `Genesis 1`, `Genesis 1:31-2:3`, `Psalm 23`,
`Song of Songs 2:1`, and `Daniel 2:4`. En/em dashes are accepted as range
separators. Multiple disjoint ranges and whole-book requests are unsupported.

A successful lookup returns fresh dictionaries with:

- `hebrew`: pointed and cantillated source text, in logical reading order.
  Source `/` morpheme and `\\` punctuation separators are removed; actual
  punctuation is retained. An orthographic word is one output token.
- `gloss`: source English word gloss with `/` prefix/root/suffix segmentation,
  implied `[words]` and translation-optional `<words>` preserved as plain text.
- `strongs`: one exact **root** dStrong identifier, such as `H7225G`. Attached
  prefix/suffix tags are not misrepresented as extra independent words.
- `lemma`: root headword from the exact TBESH entry, or TAHOT root expansion.
- `morph`: unchanged source morphology, including attached morphemes.
- `chapter`, `verse`: integers in English versification.
- `language`: `hebrew` or `aramaic`.
- `text_type`: source text indicator, e.g. `L`, `Q(K)`, or `R`.

Unknown references, inverted or partly unavailable ranges, damaged or
incomplete book files, and unavailable lexical metadata return `None`, so the
caller can use its ordinary English fallback for the **entire** passage.
The manifest's chapter/verse word counts are checked when a book is loaded.
Token shape/types are validated before rendering. At most three decompressed
books are cached; the smaller lexicon is loaded once lazily.

`get_hebrew_lexicon_entry(strongs)` returns a fresh dictionary with `hebrew`,
`translit`, `gloss`, `def`, and `definition_strongs`, or `None`. Numeric portions
are zero-padded internally; suffix case is preserved. An unknown extended
identifier never silently resolves to another disambiguated sense.

TBESH `Meaning` definitions are **not** distributed because their separate
Online Bible permission requirement differs from Tyndale's short glosses.
Instead, definitions come from the public-domain XML edition of James
Strong's 1894 dictionary at
[OpenScriptures](https://github.com/openscriptures/strongs), pinned at
`0acd2f251c2d35ff8db2dece4e0593979d3ac223`. Only original Strong explanation
(or translation) notes are extracted, not the separate BDB-style lists.
The original Strong number is broader than STEP's exact disambiguated sense:
`definition_strongs` explicitly records that source number. STEP extensions
without an original Strong entry have an empty `def` (the short gloss remains
available). Source tags, transliterations, and glosses are not AI-generated.

## Rebuild and verify

The preparation script requires only the Python standard library. Network
access is opt-in and downloads are pinned and SHA-256-verified:

```sh
python3 scripts/prepare_hebrew.py --source-dir /tmp/latexgen-hebrew-sources --download
```

After the initial download, rebuild entirely offline:

```sh
python3 scripts/prepare_hebrew.py --source-dir /tmp/latexgen-hebrew-sources
python3 scripts/prepare_hebrew.py --source-dir /tmp/latexgen-hebrew-sources --output-dir /tmp/hebrew-rebuild
```

The output contains sorted, compact JSON with UTF-8 preserved and gzip headers
with an empty filename and zero mtime. Repeated builds in the same Python/zlib
runtime produce byte-identical corpus files and manifest. The manifest records
all upstream URLs, pinned revisions, source hashes, output hashes, omitted row
counts, supplemented IDs, and per-verse token counts. The checked-in
`NOTICE.md` and full license must accompany the generated files when packaging.

```sh
data/.venv/bin/python -m pytest tests/test_hebrew_interlinear.py -q
```

Tests cover all book/verse continuity, every token's lexicon resolution,
Genesis word order and alignment, English Psalm/Joel/Malachi numbering, Qere
selection, Aramaic transitions, complete-range fallback, malformed corpus
records, cache isolation, license-sensitive extraction, and deterministic
serialization. The source's English glosses are translation aids rather than
a fluent Bible translation or an exhaustive lexical study.
