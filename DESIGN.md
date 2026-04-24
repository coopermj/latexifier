---
name: Sermon Notes PDF
description: Typeset sermon notes for the Remarkable Paper Pro — annotated critical edition format
colors:
  scholiast-purple: "#800080"
  margin-lavender: "#E6E6FA"
  codex-black: "#330033"
  rubric-red: "#ff0000"
typography:
  display:
    fontFamily: "Josefin Sans, sans-serif"
    fontSize: "\\huge (approx. 24pt on A5)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "normal"
  title:
    fontFamily: "Josefin Sans, sans-serif"
    fontSize: "\\Large (approx. 18pt)"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "All Round Gothic, sans-serif"
    fontSize: "\\normalsize (approx. 10pt)"
    fontWeight: 400
    lineHeight: 1.3
  scripture:
    fontFamily: "Latin Modern Roman, serif"
    fontSize: "\\small (approx. 9pt)"
    fontWeight: 400
    lineHeight: 1.4
  commentary:
    fontFamily: "Optima, sans-serif"
    fontSize: "\\small (approx. 9pt)"
    fontWeight: 400
    lineHeight: 1.4
  byline:
    fontFamily: "Autumn in November, Snell Roundhand, Brush Script MT, Zapfino, cursive"
    fontSize: "\\normalsize"
    fontWeight: 400
  greek:
    fontFamily: "Times New Roman, serif"
    fontSize: "\\small (approx. 9pt)"
    fontWeight: 400
spacing:
  page-margin-inner: "10mm"
  page-margin-outer: "15mm"
  page-margin-vert: "10mm"
  rule-band: "1cm"
  footer-skip: "8mm"
---

# Design System: Sermon Notes PDF

## 1. Overview

**Creative North Star: "The Annotated Critical Edition"**

This is a document in the tradition of scholarly scriptural apparatus: clean hierarchical typography, structured pages that feel composed rather than generated, and a purple that functions as ink rather than brand accent. Every page is a unit of attention — the reader comes to study, not scan, and the layout honors that. The right-side lavender rule echoes the column ruling of medieval manuscripts, here serving as both a visual anchor and a gentle reminder that this margin is workspace.

The system uses four distinct font families, each assigned a single semantic role with no overlap: rounded gothic for the pastor's voice, classical roman for scripture, geometric sans for structure and navigation, and a script for the human byline. Helvetica Neue stands apart for commentary — a deliberate sans-serif signal that "this is not the pastor's voice." The document is typeset for the Remarkable Paper Pro (A5, 229 PPI, e-ink), where no color reaches the reader except as a grayscale value. Weight, size, and whitespace carry all hierarchy.

This system explicitly rejects: church bulletin aesthetic (clip art, centered decorative fonts, drop shadows); generic PDF template look (Times New Roman 12pt, 1-inch margins, no visual hierarchy); PowerPoint handout style (bullet-heavy, low information density, large room-sized fonts); modern SaaS-clean (thin fonts, excessive whitespace, cold neutrals); study Bible populism (colored call-out boxes, pull quotes in rounded rectangles, sidebars).

**Key Characteristics:**
- Four-register font system: each family has one semantic role, never shared
- Page-as-unit composition: each sub-point owns a page, each page feels resolved
- Purple as scholarly ink: structural, never decorative
- Flat on e-ink: hierarchy through weight and scale only, no shadows
- Annotation-first margins: the outer margin is workspace, not padding

## 2. Colors: The Ink Palette

A single-accent palette derived from liturgical tradition. The purple functions as colored ink — the kind a scholar would use to annotate or rubricate — not as a brand hue.

### Primary
- **Scholiast Purple** (`#800080`): The central mark of the system. Used for all hyperlinks (TOC entries, scripture cross-references, the footer home icon), interactive states, and any navigational element. On e-ink it renders as a medium-dark gray, preserving its structural weight. Reserve it strictly for links and navigation — it signals "this is interactive."

### Secondary
- **Rubric Red** (`#ff0000`): Currently assigned to subsection headings in the LaTeX source (`mediumdark`). In the manuscript tradition, red ink (rubrication) marked structural divisions. However, on e-ink this renders identically to any other dark ink — reconsider whether a purple-adjacent dark value would be more consistent. If retained, use only at the subsection heading level, nowhere else.

### Neutral
- **Codex Black** (`#330033`): Deep purple-black for section headings. Not a neutral gray — it carries the hue of the system even at maximum darkness. Used at the top of the typographic hierarchy where weight alone is insufficient.
- **Margin Lavender** (`#E6E6FA`): The 1cm right-side rule. A pale tint that signals "annotation zone" without competing with text. On e-ink it renders as a very light gray band. Appears nowhere else in the document.

### Named Rules
**The Single Ink Rule.** Scholiast Purple and Rubric Red appear only in structural roles: links, navigation, and heading-level rubrication. They are never used for emphasis within body text, callouts, or decorative borders. Their rarity is what makes them readable as navigational signals on a grayscale screen.

**The Grayscale Contract.** Every color decision must survive a grayscale rendering. The primary differentiator on e-ink is not hue but luminance. Scholiast Purple (`#800080`) renders at approximately 20% luminance — usable for links. Margin Lavender (`#E6E6FA`) renders at approximately 91% luminance — usable as a tint band. Design for these grayscale values, not the RGB hues.

## 3. Typography: The Four-Register System

**Display/Structure Font:** Josefin Sans (geometric sans-serif)
**Body Font:** All Round Gothic (rounded humanist gothic)
**Scripture Font:** Latin Modern Roman (classical serif)
**Commentary Font:** Optima (humanist sans, lightly flared terminals)
**Byline Font:** Script cascade (Autumn in November → Snell Roundhand → Brush Script MT → Zapfino → Times New Roman Italic)
**Greek Font:** Times New Roman (polytonic-capable serif)

**Character:** The pairing is deliberately stratified. All Round Gothic's rounded terminals give the pastor's notes a personal, approachable warmth — this is a voice, not a treatise. Latin Modern Roman's classical authority signals that scripture text operates in a different register. Josefin Sans provides geometric precision for structural navigation. Helvetica Neue's neutrality signals "external voice" for commentary. The script byline is the one human mark on the title page.

### Hierarchy
- **Display** (Josefin Sans, bold, `\huge` approx. 24pt, leading 1.1): Sermon title on the title page only. Never repeated elsewhere in the document.
- **Title** (Josefin Sans, bold, `\Large` approx. 18pt, leading 1.2): Passage subtitle on the title page; "Contents" header in the TOC.
- **Section** (RM serif, bold, 14pt/16.8pt, with 0.8pt underrule): Major section headings (Sermon Notes, Commentary, Lexicon). Rendered in Codex Black. Each section starts on a new page.
- **Subsection** (RM serif, bold, 12pt/16.8pt): Point-level headings within sections. Currently rendered in Rubric Red — see color note above.
- **Body** (All Round Gothic, regular, `\normalsize` approx. 10pt, leading 1.3): All pastor's notes, bullet points, and prose content. This is the primary reading voice.
- **Scripture** (Latin Modern Roman, regular, `\small` approx. 9pt, leading 1.4): All scripture quotations. Never uses the body font. The size step down (10pt → 9pt) combined with the serif-to-body-sans contrast is the sole differentiator.
- **Commentary** (Optima, regular, `\small` approx. 9pt, leading 1.4): Commentary appendix text. The humanist sans with lightly flared terminals reads as refined rather than neutral, differentiating it from both the body and scripture voices without the coldness of a full grotesque.
- **Byline** (script cascade, `\normalsize`): Speaker name on the title page only. The only expressive typographic gesture in the system.
- **Greek** (Times New Roman, `\small`): Interlinear Greek tokens above their English glosses. Glosses are italic and hyperlinked to the lexicon.

### Named Rules
**The Four-Register Rule.** Each font family is assigned one semantic category and never appears outside it: All Round Gothic = pastor's voice; Latin Modern Roman = scripture; Josefin Sans = structure/navigation; Optima = external commentary. Mixing registers — e.g., using Josefin Sans for body text, or Latin Modern Roman for headings — breaks the semantic contract that makes the typography self-explanatory.

**The Size-Step Rule.** Scripture and commentary are set at `\small` (approx. 9pt) against the `\normalsize` (approx. 10pt) body. This 1pt step combined with font-family contrast is sufficient to signal register change. Do not increase scripture size to match the body — the step is intentional and preserves the hierarchy.

## 4. Elevation

This system is flat by design. The target device is e-ink, which renders drop shadows as dark smears and blur effects as undefined noise. No `box-shadow`, no blur, no tonal layering through opacity.

Depth is conveyed entirely through typography: weight contrast (bold headings over regular body), size contrast (display over body), font-family contrast (four registers), and spatial separation (section-break page clearing, `\vspace` divisions). The one visual-structural element that could be called "elevation" is the Margin Lavender rule — a 1cm band at the right edge of each page, rendered as a solid tint. It reads as a physical column ruling, not a shadow.

### Named Rules
**The Flat-and-Final Rule.** If a layout problem seems to call for a box, border, background tint, or shadow, the correct answer is almost always a typographic solution instead: a weight increase, a font switch, a page break, or additional vertical space. Boxes and borders in a PDF designed for e-ink add visual noise without adding hierarchy.

## 5. Components

### Title Block
The title page is a single composed unit, not a template. Four typographic levels read as a single statement: title → passage → name → date.
- **Title:** Josefin Sans, `\huge`, bold, flush left
- **Passage (subtitle):** Josefin Sans, `\Large`, flush left, immediately below with 0.3cm gap
- **Speaker name:** Script font (cascade), flush left — the single expressive gesture, a calligraphic personal mark
- **Date:** Josefin Sans, regular, flush left
- **Cover image (optional):** Centered, capped at 75% text width and 38% text height, `keepaspectratio`. Placed between title block and TOC using `\vfill` so vertical space distributes naturally. Never overflows the title page.
- **TOC:** Josefin Sans bold "Contents" label, centered; entries as a plain `tabular` with hyperlinks, no rules, 0.3cm between entries.

### Scripture + Notes Layout (Paracol)
The core content pattern: 48/52 column split using `paracol`. Left column = scripture (Latin Modern Roman, `\small`, `\raggedright`). Right column = pastor's notes (body font). Columns can break across pages. The split is deliberately unequal — scripture at 48% is slightly narrower, signaling that it is the anchor, not the dominant column.

### Interlinear Word Stack
Each Greek word is a vertical unit: Greek token above (`\greekfont\small`), English gloss below (`\scriptsize\italic`, hyperlinked to lexicon). Words are set in a horizontal flow with 5pt inter-word spacing. Verse breaks are marked by a verse number prefix. The entire interlinear occupies the left column of a 50/50 paracol, with the clean English translation in the right column.

### Commentary Block
Set entirely in Helvetica Neue at `\small`. Source attribution appears as a section heading with an 0.8pt underrule. Each entry carries a `\hypertarget` for the return-link system. The source name and verse range appear at the entry head; body text follows in regular weight. A `↩` glyph at the close of each entry hyperlinks back to the note page that referenced it.

### Commentary Links Footer (Note Pages)
When a note page has associated commentary entries, a `\vfill` + thin 0.4pt rule anchors an inline apparatus line at the page bottom. Links appear as a horizontal sequence in `\footnotesize\commentaryfont` (Optima), separated by centered dots (`\textperiodcentered`), colored in Scholiast Purple. Per source, only the most specific (smallest verse range) matching entry is shown — no duplicate broad-range entries from the same source. The rule matches the footer rule visually, making the apparatus feel like an extension of the footer rather than a separate element.

### Footer Navigation
A `fancypagestyle` footer on every non-title page: 0.4pt horizontal rule above; Scholiast Purple `\faHome` glyph at left (hyperlinked to title page); page number at right. Footskip 8mm. No header rule. The home icon is the only navigational chrome visible during reading.

## 6. Do's and Don'ts

### Do:
- **Do** set the speaker name in the script cascade (`\qtcoronation`) — it is the only expressive typographic gesture and earns its place by making the document personal.
- **Do** use `\vfill` to distribute vertical space on the title page. Fixed `\vspace` values cause overflow when a cover image is present. Let TeX breathe.
- **Do** cap cover images at `width=0.75\textwidth, height=0.38\textheight, keepaspectratio`. The title page must never overflow onto a second page.
- **Do** start each section on a new page (`\clearpage\oldsection`). The section break is structural, not optional.
- **Do** use the 48/52 paracol split for scripture/notes, not 50/50. The asymmetry signals which column is anchor and which is commentary.
- **Do** keep all link colors as Scholiast Purple (`#800080`). On e-ink, links are the only in-document navigation; they must be visually consistent.
- **Do** test every color and spacing decision against its grayscale rendering. The Remarkable Paper Pro is the primary reading device.

### Don't:
- **Don't** use clip art, borders, drop shadows, background color fills, or decorative elements anywhere in the document. This is not a church bulletin.
- **Don't** use Times New Roman 12pt with 1-inch margins and no hierarchy. The generic PDF template look is the specific failure mode this system exists to avoid.
- **Don't** use bullet-heavy layouts with large fonts sized for projection or a room. This document is for close individual reading at 229 PPI.
- **Don't** add colored call-out boxes, pull quotes in rounded rectangles, sidebars, or any study Bible populism. Content hierarchy is typographic, not spatial-decorative.
- **Don't** mix font-family roles. All Round Gothic is the pastor's voice; it does not appear in headings, scripture, or commentary. Latin Modern Roman is scripture; it does not appear in body notes or headings.
- **Don't** use the body font (All Round Gothic) for scripture quotations. The semantic register distinction between scripture and notes is carried by the font switch — removing it collapses the hierarchy.
- **Don't** use thin fonts, excessive whitespace, or cold neutral grays. The aesthetic is warm scholarly weight, not SaaS minimalism.
- **Don't** use gradient text, glassmorphism, or any CSS-era web pattern in the PDF. There is no CSS; there is only LaTeX, and these patterns have no equivalent.
- **Don't** ignore the e-ink grayscale contract. Any design choice that depends on the reader seeing `#800080` as purple (rather than as a medium-dark gray) is a choice that fails on the actual device.
