# Bundled scripture assets

Every compile path copies these runtime assets after user-managed storage
styles and fonts. This pins `scripture.sty` even when the TeX distribution
or `/data/styles` contains an older version. Docker already copies `app/`.
The assets are also required beside a downloaded sermon TeX file when compiling
that source independently (along with the existing sermon fonts).

- `scripture.sty`: CTAN **2.5, 2026-08-23**, downloaded from
  <https://mirrors.ctan.org/macros/latex/contrib/scripture.zip> on 2026-09-13.
  Upstream sources, installer and license notice are in `upstream/`.
  Generated with `tex scripture.ins`; `upstream/scripture-local.patch` retains
  Geneva's vertical-mode verse-mark penalty. This is a locally modified copy.
  To regenerate, run the installer in `upstream/`, apply the patch there,
  then replace the runtime copy. Do not replace it with an unpatched release.
- `verse_protrusion.tex`: from `geneve_1564` at `cf87dfd`, adapted to detect
  superior figures **after selecting the scripture font**, inside its font
  hook. It retains the 350/1000 left protrusion and default punctuation tables.
- `biblical-hyphenation.tex`: the generated exception list from that checkout's
  `line_breaking.tex`, derived from Scribe's Bible list and Potts (1922).
  `latexgen-scripture.sty` applies tolerance 400, emergency stretch 1em and
  both hyphen demerits 7500 locally rather than to sermon notes.
- Four `EBGaramond-*.otf` faces: byte-for-byte copies of the Geneva project's
  fonts, selected by filename to avoid stale or mismatched installed fonts.
  See `upstream/EBGaramond-OFL.txt` for the SIL Open Font License.
- Ten `JosefinSans-*.otf` faces: byte-for-byte copies of the user's supplied
  hidden `.15622.otf` through `.15631.otf` files in `josefin/`. No conversion
  was needed. `latexgen-josefin.sty` selects Regular, Bold, Italic and Bold Italic
  by filename for the title, subtitle, date and contents heading. Light, Thin and
  SemiBold faces are retained alongside them. Source mappings and hashes are in
  `upstream/JosefinSans-manifest.json`; copyright and license are in
  `upstream/JosefinSans-NOTICE.txt` and `upstream/JosefinSans-OFL.txt`.
- `SnellRoundhand.otf` and `SnellRoundhand-Bold.otf`: byte-for-byte copies from
  the supplied `SnellRoundhand/Variable-PS/` folder. `latexgen-snell.sty` selects
  these files for the author line. They contain static CFF outlines and need no
  conversion or operating-system font installation.
- `SILEOT.ttf`: unmodified Ezra SIL 2.51 for Hebrew and Aramaic. Selected by
  filename with HarfBuzz shaping in `latexgen-hebrew.sty`. Hebrew paragraphs run
  right to left while each gloss stays left to right. See `EzraSIL-LICENSE.txt`
  and `docs/hebrew-interlinear.md` for the source archive and checksum.
- `upstream/geneve-LICENSE`: source project's GPLv3 license.
- `upstream/SHA256SUMS`: snapshot hashes for asset review.

Chapter numbers use native two-line drop caps with bold lining figures, as
requested on 2026-09-13. Native scripture headings retain their space reservation.
Chapters immediately before poetry move inside it so the drop cap sits beside
the opening lines. Poetry skips use the current baseline;
sermon page dimensions and non-scripture typography retain their own settings.
First verse numbers stay visible because this project does not use book initials.
