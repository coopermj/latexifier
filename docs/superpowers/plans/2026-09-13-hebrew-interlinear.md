# Hebrew interlinear

Extend the existing automatic Greek interlinear to Old Testament main passages.
Keep the English passage beside word-stacked Hebrew, reading right to left with
English glosses reading left to right. Link glosses to a Hebrew lexicon appendix.
Bundle the complete source corpus, lexicon, font and attribution inside the app;
generation must not depend on Codex or a new remote lookup. Retain the existing
Greek workflow, native scripture poetry and slide enrichment.

1. Prepare a reproducible, pinned import of an attributed Hebrew/Aramaic corpus
   with English glosses, Strong's identifiers and morphology. Preserve source
   verse mappings and document the selected source readings. Implement local reference lookup for
   single verses, ranges, chapters and cross-chapter ranges; fail closed on gaps.
2. Add bundled Hebrew font and LuaLaTeX right-to-left word stacks. Integrate
   automatic selection, contents links and Hebrew lexicon with H-prefixed links.
3. Test source import, passage lookup and rendering. Compile real Hebrew and
   mixed-direction samples, verify reading order and links, and rebuild the
   supplied Isaiah sermon with slides. Run the complete existing suite.
4. Review source coverage, distribution/licensing, rendering and regressions.

The implementation is authorized by the user's request. Routine design choices
will be resolved through source evidence and rendered PDF inspection.
