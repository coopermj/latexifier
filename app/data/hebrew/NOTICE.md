# Hebrew interlinear data attribution

TAHOT (Translators Amalgamated Hebrew Old Testament) text, English word glosses,
morphology, root tags, and TBESH (Translators Brief lexicon of Extended Strongs
for Hebrew) Hebrew headwords, transliterations, and short glosses:

**Data created by STEPBible.org based on work at Tyndale House, Cambridge.**
Copyright the respective contributors; licensed under **Creative Commons
Attribution 4.0 International (CC BY 4.0)**.

Source: https://github.com/STEPBible/STEPBible-Data
Pinned revision: `ae39711d7843b2902d54993e432de9c12d6a4b9a`.
License: https://creativecommons.org/licenses/by/4.0/
The complete license is included in `LICENSE-CC-BY-4.0.txt`.

TAHOT derives its Hebrew from Westminster Leningrad Codex 4.20 via
OpenScriptures, checked/corrected by Tyndale scholars against Leningrad/BHS.
Its morphology derives from ETCBC with Tyndale adaptations.

**Changes in this adaptation:** selected the principal word-per-line text
(Leningrad/Qere/restored text); omitted Ketiv/other variant columns, 152
reconstructed LXX additions and 14 empty Qere omissions; removed Hebrew
morpheme/punctuation separator slashes while retaining the actual characters;
kept English gloss segmentation; selected each orthographic word's root tag;
used leading English references and retained Psalm superscriptions as verse 0;
reformatted as compact per-book gzip JSON. For 14 extended TAHOT identifiers absent as
exact TBESH entries, headword/gloss metadata comes from TAHOT's expanded root
tags; seven other missing TBESH identifiers use their original Strong entries. The manifest lists those identifiers. No claim of STEPBible endorsement
is made.

TBESH's **Meaning** column includes Online Bible material with a separate
permission requirement. **That column is excluded from this distribution.**

## Dictionary definitions

James Strong, *A Concise Dictionary of the Words in the Hebrew Bible, with
their Renderings in the King James Version* (1894). Electronic source edited
by David Instone-Brewer and David Troidl, distributed by OpenScriptures.
The source XML header declares **Public Domain**.

Source: https://github.com/openscriptures/strongs
Pinned revision: `0acd2f251c2d35ff8db2dece4e0593979d3ac223`.
Source file: `hebrew/StrongHebrewG.xml`.

Only original Strong `explanation` notes (or `translation` notes where an
explanation is absent), plus lemma/transliteration fallback metadata are used.
The XML's separate BDB-style `list` entries are excluded. Inline XML formatting
is converted to plain text. These definitions describe the original broad
Strong number, not necessarily an individual STEP disambiguated sense; the
`definition_strongs` field identifies that number. Some STEP-only extensions
have no original Strong definition and therefore an empty definition.

All upstream URLs and SHA-256 checksums are retained in `manifest.json`.
See `docs/hebrew-data.md` and `scripts/prepare_hebrew.py` for the reproducible
build and precise runtime contract.
