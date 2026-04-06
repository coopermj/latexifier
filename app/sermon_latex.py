"""Generate LaTeX from parsed sermon outline."""
import json
import logging
from pathlib import Path

from .models import SermonOutline, SermonPoint, SermonSubPoint, Table
from .commentary import CommentarySource, fetch_commentary_for_reference, CommentaryResult
from .scripture import fetch_scripture, ScriptureVersion, ScriptureLookupOptions
from .lsj import get_lsj_entry
from .interlinear import get_passage_words, is_nt_passage

logger = logging.getLogger(__name__)

# Load Strong's Greek data
STRONGS_GREEK = {}
strongs_path = Path(__file__).parent / "strongs_greek.json"
if strongs_path.exists():
    try:
        STRONGS_GREEK = json.loads(strongs_path.read_text())
    except Exception as e:
        logger.warning("Failed to load Strong's Greek data: %s", e)


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in text."""
    if not text:
        return ""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


_MORPH_PREFIX = {
    "N": "noun", "V": "verb", "A": "adj.", "ADV": "adv.",
    "PREP": "prep.", "CONJ": "conj.", "ART": "art.", "T": "art.",
    "P": "pron.", "PRT": "part.", "INJ": "interj.",
}


def _morph_label(morph: str) -> str:
    """Convert a Berean morphology code prefix to a readable label."""
    prefix = morph.split("-")[0].upper()
    return _MORPH_PREFIX.get(prefix, morph.lower())


def scripture_placeholder(reference: str, version: str, nolinks: bool = False, strongs_overlay: bool = False) -> str:
    """Generate a scripture placeholder string."""
    if nolinks:
        return f"[[scripture:{reference}|{version}|nolinks=true]]"
    if strongs_overlay:
        return f"[[scripture:{reference}|{version}|strongs_overlay=true]]"
    return f"[[scripture:{reference}|{version}]]"


def _render_table(table: Table) -> list[str]:
    """Render a table as LaTeX tabularx environment with text wrapping."""
    lines = []

    if not table.headers:
        return lines

    num_cols = len(table.headers)
    # Use X columns for auto-width with text wrapping
    col_spec = "|" + "X|" * num_cols

    lines.append("")
    if table.caption:
        lines.append(rf"\textbf{{{escape_latex(table.caption)}}}")
        lines.append(r"\vspace{0.3cm}")
        lines.append("")

    # Use tabularx with \textwidth for proper margins
    lines.append(rf"\begin{{tabularx}}{{\textwidth}}{{{col_spec}}}")
    lines.append(r"\hline")

    # Header row (bold)
    header_cells = [rf"\textbf{{{escape_latex(h)}}}" for h in table.headers]
    lines.append(" & ".join(header_cells) + r" \\")
    lines.append(r"\hline")

    # Data rows
    for row in table.rows:
        # Pad row if needed
        cells = list(row) + [""] * (num_cols - len(row))
        escaped_cells = [escape_latex(c) for c in cells[:num_cols]]
        lines.append(" & ".join(escaped_cells) + r" \\")
        lines.append(r"\hline")

    lines.append(r"\end{tabularx}")
    lines.append(r"\vspace{0.5cm}")
    lines.append("")

    return lines


def _render_interlinear_passage(
    words: list[dict],
    main_passage: str,
    scripture_version: str,
) -> list[str]:
    """
    Render a 50/50 paracol block: interlinear (left) + clean ESV (right).

    words: output of interlinear.get_passage_words() — each has
           greek, lemma, strongs, gloss, morph, verse (int)
    """
    lines = []
    lines.append(r"\newpage{}")
    lines.append(r"\hypertarget{interlinear}{}")
    lines.append(r"\columnratio{0.5}")
    lines.append(r"\setlength{\columnsep}{1.5em}")
    lines.append(r"\begin{paracol}{2}")
    lines.append(r"\small\raggedright")
    lines.append("")

    # Left column: word-stacked interlinear grouped by verse
    current_verse = None
    for w in words:
        if w["verse"] != current_verse:
            if current_verse is not None:
                lines.append("")  # spacing between verses
            current_verse = w["verse"]
            lines.append(rf"{{\color{{gray}}\scriptsize {current_verse}}}~")
        greek = escape_latex(w["greek"])
        gloss = escape_latex(w["gloss"])
        strongs = w["strongs"]
        lines.append(rf"\intword{{{greek}}}{{{gloss}}}{{{strongs}}}")

    lines.append("")
    lines.append(r"\switchcolumn")
    lines.append(r"\raggedright")
    lines.append(scripture_placeholder(main_passage, scripture_version, nolinks=True))
    lines.append("")
    lines.append(r"\end{paracol}")
    lines.append(r"\newpage{}")
    return lines


def _render_lexicon_appendix(passage_words: list[dict]) -> list[str]:
    """
    Render the Lexicon section with one rich entry per unique Strong's number.

    Entry format:
      Greek (large) + transliteration  [right-aligned: G-number]
      grammatical form --- Strong's definition (italic)
      L&S: <entry text>   (omitted if no LSJ entry exists)
    """
    if not passage_words:
        return []

    # Build Strong's → first morph code seen (for grammatical label)
    morph_for: dict[str, str] = {}
    for w in passage_words:
        num = w.get("strongs", "")
        if num and num not in morph_for:
            morph_for[num] = w.get("morph", "")

    strongs_numbers = {w["strongs"] for w in passage_words if w.get("strongs")}
    if not strongs_numbers:
        return []

    lines = []
    lines.append("")
    lines.append(r"\newpage{}")
    lines.append(r"\newgeometry{left=10mm,right=15mm,top=15mm,bottom=10mm}")
    lines.append(r"\hypertarget{lexicon}{}")
    lines.append(r"\section{Lexicon}")
    lines.append(r"\greekfont\small")
    lines.append("")

    for num in sorted(strongs_numbers, key=lambda x: int(x)):
        entry = STRONGS_GREEK.get(num)
        if not entry:
            continue

        greek    = entry.get("greek", "")
        translit = entry.get("translit", "")
        defn     = escape_latex(entry.get("def", ""))
        gram     = _morph_label(morph_for.get(num, ""))

        lsj_text = get_lsj_entry(num)

        lines.append(r"\vspace{8pt}")
        lines.append(r"\begin{minipage}{\linewidth}")
        lines.append(r"\raggedright")
        lines.append(rf"\hypertarget{{lex-{num}}}{{}}")
        # Header: Greek (large) + translit, G-number right-aligned
        lines.append(
            rf"{{\greekfont\large {greek}}}\quad"
            rf"{{\greekfont\itshape {escape_latex(translit)}}}"
            rf"\hfill{{\greekfont\textbf{{G{num}}}}}"
        )
        lines.append(r"\hrule\vspace{4pt}")
        # Definition line: grammatical form + Strong's definition
        lines.append(rf"{{\greekfont\small {escape_latex(gram)} --- \textit{{{defn}}}}}")

        # L&S block with left rule for visual separation (optional)
        if lsj_text:
            lines.append(r"\smallskip")
            lines.append(
                r"\noindent{\color{gray}\vrule width 1.5pt}\hspace{6pt}"
                rf"\parbox{{\dimexpr\linewidth-10pt}}{{\raggedright\greekfont\small "
                rf"\textbf{{Liddell \& Scott}} --- {escape_latex(lsj_text)}}}"
            )

        lines.append(r"\end{minipage}")

    lines.append(r"\restoregeometry")
    return lines


def format_date(date_str: str | None) -> str:
    """Convert date to long format like 'January 23, 2026'."""
    if not date_str:
        return ""
    import re
    from datetime import datetime

    # Try to parse common formats like "1/11/26" or "01/11/2026"
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
    if match:
        month, day, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime("%B %d, %Y")
        except ValueError:
            pass
    return date_str


async def generate_sermon_latex(
    outline: SermonOutline,
    scripture_version: str = "ESV",
    subpoint_version: str = "NET",
    include_main_passage: bool = True,
    cover_image: str | None = None,
    commentary_sources: list[str] | None = None,
    commentary_overrides: list[CommentaryResult] | None = None,
    include_bulletin: bool = False,
    include_prayer_requests: bool = False
) -> str:
    """
    Generate LaTeX document from sermon outline.

    Args:
        outline: Parsed sermon outline
        scripture_version: Bible version for main passage and foundational scripture
        subpoint_version: Bible version for sub-point scriptures (default NET)
        include_main_passage: Whether to include full main passage text
        cover_image: Optional filename of cover image (must be in work directory)
        commentary_sources: List of commentary sources to include (mhc, calvincommentaries)
        commentary_overrides: Pre-fetched CommentaryResult objects to use directly, bypassing DB fetch
        include_bulletin: Whether bulletin PDF is included (adds TOC entry and includes it)
        include_prayer_requests: Whether prayer requests PDF is included (adds TOC entry and includes it)

    Returns:
        Complete LaTeX document as string
    """
    lines = []
    title = escape_latex(outline.metadata.title or "")
    speaker = escape_latex(outline.metadata.speaker or "")
    date = format_date(outline.metadata.date)
    main_passage = outline.main_passage

    # Preamble
    lines.append(r"""\documentclass[
  letterpaper,
  DIV=11,
  numbers=noendperiod
]{scrartcl}

% Layout / numbering
\KOMAoptions{parskip=half}
\setcounter{secnumdepth}{-\maxdimen}
\setlength{\emergencystretch}{3em}

\usepackage[
  a5paper,
  total={196mm,274mm},
  left=10mm,
  top=10mm,
  bottom=10mm,
  right=15mm
]{geometry}

% Color + graphics + positioning
\usepackage[dvipsnames,svgnames,x11names]{xcolor}
\usepackage{graphicx}
\usepackage{eso-pic}
\usepackage{float}

% Headers/footers
\usepackage{fancyhdr}

% Fonts + heading styling
\usepackage{fontspec}
\usepackage{sectsty}
\usepackage{titlesec}

% Scripture quotations
\usepackage{scripture}

% Multi-column layout for main passage
\usepackage{multicol}

% Tables with auto-width columns
\usepackage{tabularx}

% Parallel columns that can break across pages
\usepackage{paracol}

% FontAwesome icons
\usepackage{fontawesome5}

% Microtypography
\usepackage[protrusion=true,expansion=true,verbose=silent]{microtype}

% PDF metadata / links
\usepackage{hyperref}

% Include external PDFs
\usepackage{pdfpages}

% Pandoc list helper
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}%
}

% Two-column scripture + notes (using paracol for page breaks)
\newcommand{\scripturebullets}[2]{%
  \columnratio{0.48}
  \begin{paracol}{2}
    \raggedright
    #1
  \switchcolumn
    \raggedright
    #2
  \end{paracol}
}

% Interlinear word unit: Greek above, linked English gloss below
\newcommand{\intword}[3]{%
  \begin{tabular}[t]{@{}c@{}}
    {\greekfont\small #1}\\[1pt]
    \hyperlink{lex-#3}{\scriptsize\textit{#2}}%
  \end{tabular}\hspace{5pt}%
}

% Colors
\definecolor{light}{HTML}{E6E6FA}
\definecolor{highlight}{HTML}{800080}
\definecolor{dark}{HTML}{330033}
\definecolor{mediumdark}{HTML}{ff0000}

% Right-side border + logo
\AddToShipoutPicture{%
  \AtPageLowerLeft{%
    \put(\LenToUnit{\dimexpr\paperwidth-1cm},0){%
      \color{light}\rule{1cm}{\LenToUnit\paperheight}%
    }%
  }%
}

% Page number style with home icon and rule
\fancypagestyle{mystyle}{%
  \fancyhf{}%
  \renewcommand\headrulewidth{0pt}%
  \renewcommand\footrulewidth{0.4pt}%
  \fancyfoot[L]{\hyperlink{titlepage}{\color{highlight}\faHome}}%
  \fancyfoot[R]{\thepage}%
}
\setlength{\footskip}{8mm}

% Fonts
% Main document font - All Round Gothic (for sermon notes, not scripture)
\setmainfont{37144.otf}[
  Path = ./,
  BoldFont = 37150.otf,
  ItalicFont = 37145.otf,
  BoldItalicFont = 37151.otf,
  Ligatures = TeX
]
% Serif font for scripture quotations (Computer Modern Roman)
\newfontfamily\scripturefont{Latin Modern Roman}
\newfontfamily\wordstudy{Times New Roman}
\newfontfamily\greekfont{Times New Roman}
\newfontfamily\josefin{Josefin Sans}
\newfontfamily\commentaryfont{BanglaMN.ttf}[
  Path = ./,
  BoldFont = BanglaMN-Bold.ttf
]
\IfFontExistsTF{Autumn in November}
  {\newfontfamily\qtcoronation{Autumn in November}}
  {\IfFontExistsTF{Snell Roundhand}
    {\newfontfamily\qtcoronation{Snell Roundhand}}
    {\IfFontExistsTF{Brush Script MT}
      {\newfontfamily\qtcoronation{Brush Script MT}}
      {\IfFontExistsTF{Zapfino}
        {\newfontfamily\qtcoronation{Zapfino}}
        {\newfontfamily\qtcoronation{Times New Roman Italic}}}}}

% Heading styles
\sectionfont{\color{dark}\fontsize{14}{16.8}\selectfont}
\subsectionfont{\color{mediumdark}\fontsize{12}{16.8}\selectfont}
\titleformat{\section}
  {\rmfamily\large\bfseries}{\thesection}{1em}{}[{\titlerule[0.8pt]}]

% Start each section on a new page
\let\oldsection\section
\renewcommand\section{\clearpage\oldsection}

% Custom title block
\makeatletter
\renewcommand{\maketitle}{%
  \bgroup\setlength{\parindent}{0pt}%
  \begin{flushleft}
    {\josefin{\huge\textbf{\@title}}}\vspace{0.3cm}\newline
    {\josefin{\Large \@subtitle}}\newline
    \qtcoronation{\@author}\newline
    {\josefin\@date}%
  \end{flushleft}%
  \egroup
}
\makeatother
""")

    # Format main passage for subtitle (with actual Unicode en-dash)
    main_passage_display = main_passage.replace("-", "–") if main_passage else ""

    # Hypersetup and metadata
    lines.append(rf"""
\hypersetup{{
  pdftitle={{{title}}},
  pdfauthor={{{speaker}}},
  colorlinks=true,
  linkcolor={{highlight}},
  filecolor={{Maroon}},
  citecolor={{Blue}},
  urlcolor={{highlight}},
  pdfcreator={{LaTeX via pandoc}},
  breaklinks=true
}}

\title{{{title}}}
\subtitle{{{main_passage_display}}}
\author{{{speaker}}}
\date{{{date}}}

\begin{{document}}
\hypertarget{{titlepage}}{{}}
\maketitle
\pagestyle{{mystyle}}
""")

    # Add cover image if provided
    if cover_image:
        lines.append("")
        lines.append(r"\vspace{1cm}")
        lines.append(r"\begin{center}")
        lines.append(rf"\includegraphics[width=0.8\textwidth,height=0.5\textheight,keepaspectratio]{{{cover_image}}}")
        lines.append(r"\end{center}")

    # Determine interlinear eligibility before building TOC
    nt_passage = include_main_passage and bool(main_passage) and is_nt_passage(main_passage)
    passage_words = get_passage_words(main_passage) if nt_passage else None
    interlinear_active = nt_passage and passage_words is not None

    # Add table of contents
    lines.append("")
    lines.append(r"\vspace{1cm}")
    lines.append(r"\begin{center}")
    lines.append(r"{\josefin\large\textbf{Contents}}")
    lines.append(r"\end{center}")
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tabular}{l}")
    if interlinear_active:
        lines.append(r"\hyperlink{interlinear}{Greek Interlinear} \\[0.3cm]")
    lines.append(r"\hyperlink{sermonnotes}{Sermon Notes} \\[0.3cm]")
    if commentary_sources or commentary_overrides is not None:
        lines.append(r"\hyperlink{commentary}{Commentary} \\[0.3cm]")
    if interlinear_active:
        lines.append(r"\hyperlink{lexicon}{Lexicon} \\[0.3cm]")
    if include_bulletin:
        lines.append(r"\hyperlink{bulletin}{Sunday Bulletin} \\[0.3cm]")
    if include_prayer_requests:
        lines.append(r"\hyperlink{prayer}{Prayer Requests} \\[0.3cm]")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")

    lines.append("")
    lines.append(r"\newpage{}")
    lines.append("")

    # Main passage: interlinear (NT) or multicols ESV (OT/fallback)
    if include_main_passage and main_passage:
        if interlinear_active:
            lines.extend(_render_interlinear_passage(passage_words, main_passage, scripture_version))
        else:
            lines.append(r"\begin{multicols}{2}")
            lines.append(scripture_placeholder(main_passage, scripture_version))
            lines.append(r"\end{multicols}")
            lines.append("")
            lines.append(r"\newpage{}")
            lines.append("")

    # Sermon notes hypertarget for ToC link
    lines.append(r"\hypertarget{sermonnotes}{}")

    # Foundational principle as a section
    if outline.foundational_principle:
        lines.append(r"\section{Foundational Principle}")
        lines.append("")
        principle_text = escape_latex(outline.foundational_principle)
        if outline.foundational_scripture:
            lines.append(rf"{principle_text} \emph{{({escape_latex(outline.foundational_scripture)})}}")
        else:
            lines.append(principle_text)
        lines.append("")

        # Include foundational scripture text
        if outline.foundational_scripture:
            lines.append(scripture_placeholder(outline.foundational_scripture, scripture_version))
            lines.append("")

        lines.append(r"\vspace{2.2in}")
        lines.append("")

    # Main points as sections (tables render inline within each point)
    for point in outline.points:
        lines.extend(_render_point(point, subpoint_version))

    # Render any top-level tables not associated with a specific point
    if outline.tables:
        lines.append(r"\vspace{0.5cm}")
        for table in outline.tables:
            lines.extend(_render_table(table))

    # Commentary appendix
    if commentary_sources or commentary_overrides is not None:
        lines.append(r"\hypertarget{commentary}{}")
        commentary_lines = await _render_commentary_appendix(
            main_passage,
            commentary_sources or [],
            preloaded=commentary_overrides,
        )
        lines.extend(commentary_lines)

    # Lexicon appendix (NT passages only)
    if interlinear_active and passage_words:
        lines.extend(_render_lexicon_appendix(passage_words))

    # Include bulletin PDF if provided
    if include_bulletin:
        lines.append("")
        lines.append(r"\newpage")
        lines.append(r"\hypertarget{bulletin}{}")
        lines.append(r"\includepdf[pages=-,pagecommand={\thispagestyle{mystyle}}]{bulletin.pdf}")

    # Include prayer requests PDF if provided
    if include_prayer_requests:
        lines.append("")
        lines.append(r"\newpage")
        lines.append(r"\hypertarget{prayer}{}")
        lines.append(r"\includepdf[pages=-,pagecommand={\thispagestyle{mystyle}}]{prayer_requests.pdf}")

    lines.append(r"\end{document}")

    return "\n".join(lines)


def _render_point(point: SermonPoint, version: str) -> list[str]:
    """Render a main sermon point as a section."""
    lines = []
    section_title = escape_latex(point.title or "")

    # If point has sub-points, each sub-point gets its own page with section header
    if point.sub_points:
        for sub in point.sub_points:
            lines.extend(_render_subpoint(sub, version, section_title))
        # Render any tables within this point after the sub-points
        if point.tables:
            for table in point.tables:
                lines.extend(_render_table(table))
    else:
        # Point with no sub-points
        lines.append(r"\newpage{}")
        lines.append(rf"\section{{{section_title}}}")
        lines.append("")

        # Build notes content
        note_lines = []
        if point.content:
            note_lines.append(escape_latex(point.content))
            note_lines.append("")

        # Render bullets if present (simple bullet lists without letters)
        if point.bullets:
            note_lines.append(r"\begin{itemize}")
            note_lines.append(r"\setlength{\itemsep}{10pt}")
            for bullet in point.bullets:
                note_lines.append(rf"\item {escape_latex(bullet)}")
            note_lines.append(r"\end{itemize}")

        # Render numbered items if present (enumerated lists)
        if point.numbered_items:
            note_lines.append(r"\begin{enumerate}")
            note_lines.append(r"\setlength{\itemsep}{10pt}")
            for item in point.numbered_items:
                # Check if item has bold title pattern like "Title: explanation"
                if ": " in item:
                    parts = item.split(": ", 1)
                    note_lines.append(rf"\item \textbf{{{escape_latex(parts[0])}:}} {escape_latex(parts[1])}")
                else:
                    note_lines.append(rf"\item {escape_latex(item)}")
            note_lines.append(r"\end{enumerate}")

        if point.scripture_refs:
            # Two-column layout: scripture on left, notes on right
            scripture_lines = []
            for i, ref in enumerate(point.scripture_refs):
                if i > 0:
                    scripture_lines.append("")
                    scripture_lines.append(r"\vspace{0.5cm}")
                    scripture_lines.append("")
                scripture_lines.append(scripture_placeholder(ref, version, nolinks=True))
            scripture_lines.append(r"\vspace{2in}")
            scripture_content = "\n".join(scripture_lines)

            note_lines.append(r"\vspace{2in}")
            notes_content = "\n".join(note_lines)

            lines.append(r"\scripturebullets")
            lines.append(r"{%")
            lines.append(scripture_content)
            lines.append(r"}%")
            lines.append(r"{%")
            lines.append(notes_content)
            lines.append(r"}%")
        else:
            # Full-width layout (no scripture)
            lines.extend(note_lines)

        # Render any tables within this point
        if point.tables:
            for table in point.tables:
                lines.extend(_render_table(table))

    return lines


def _render_subpoint(sub: SermonSubPoint, version: str, section_title: str = "") -> list[str]:
    """Render a sub-point - two-column if has scripture refs, full-width otherwise."""
    lines = []

    # Each sub-point starts on a new page
    lines.append(r"\newpage{}")

    # Section header at top of each sub-point page
    if section_title:
        lines.append(rf"\section{{{section_title}}}")
        lines.append("")

    sub_title = escape_latex(sub.title) if sub.title else ""
    if sub.label:
        sub_title = f"{sub.label}. {sub_title}"
    lines.append(rf"\subsection{{{sub_title}}}")
    lines.append("")

    # Check if this sub-point has scripture references
    has_scripture = sub.scripture_verse or sub.scripture_refs

    if has_scripture:
        # Build scripture content (nolinks=True for paracol compatibility)
        scripture_lines = []
        if sub.scripture_verse:
            scripture_lines.append(scripture_placeholder(sub.scripture_verse, version, nolinks=True))
        if sub.scripture_refs:
            for ref in sub.scripture_refs:
                if scripture_lines:
                    scripture_lines.append("")
                    scripture_lines.append(r"\vspace{0.5cm}")
                    scripture_lines.append("")
                scripture_lines.append(scripture_placeholder(ref, version, nolinks=True))
        scripture_lines.append(r"\vspace{2in}")
        scripture_content = "\n".join(scripture_lines)

        # Build notes content
        note_lines = []
        if sub.content:
            note_lines.append(escape_latex(sub.content))
            note_lines.append("")

        if sub.bullets:
            note_lines.append(r"\begin{itemize}")
            note_lines.append(r"\setlength{\itemsep}{10pt}")
            for bullet in sub.bullets:
                note_lines.append(rf"\item {escape_latex(bullet)}")
            note_lines.append(r"\end{itemize}")

        note_lines.append(r"\vspace{2in}")
        notes_content = "\n".join(note_lines)

        # Two-column layout with paracol (links stripped for compatibility)
        lines.append(r"\scripturebullets")
        lines.append(r"{%")
        lines.append(scripture_content)
        lines.append(r"}%")
        lines.append(r"{%")
        lines.append(notes_content)
        lines.append(r"}%")
    else:
        # Full-width layout (no scripture)
        if sub.content:
            lines.append(escape_latex(sub.content))
            lines.append("")

        if sub.bullets:
            lines.append(r"\begin{itemize}")
            lines.append(r"\setlength{\itemsep}{20pt}")
            for bullet in sub.bullets:
                lines.append(rf"\item {escape_latex(bullet)}")
            lines.append(r"\end{itemize}")

    lines.append("")
    return lines


def _render_word_study_from_strongs(strongs_numbers: set[str]) -> list[str]:
    """Render Greek Word Study appendix from Strong's numbers extracted from NET Bible."""
    lines = []

    if not strongs_numbers:
        return lines

    # Filter to only numbers we have data for
    valid_numbers = [num for num in sorted(strongs_numbers, key=lambda x: int(x)) if num in STRONGS_GREEK]

    if not valid_numbers:
        return lines

    lines.append("")
    lines.append(r"\newpage{}")
    lines.append(r"\newgeometry{left=10mm,right=15mm,top=15mm,bottom=10mm}")
    lines.append(r"\section{Greek Word Study}")
    lines.append("")
    lines.append(r"\wordstudy")
    lines.append("")

    for num in valid_numbers:
        entry = STRONGS_GREEK[num]
        greek = entry.get('greek', '')
        translit = entry.get('translit', '')
        definition = entry.get('def', '')

        lines.append(r"\vspace{20pt}")
        lines.append("")
        # Add hypertarget for linking from scripture text, with wordstudy font
        lines.append(rf"\hypertarget{{strongs-{num}}}{{{{\wordstudy\textbf{{G{num}}}}}}} --- {{\greekfont {greek}}} ({{\wordstudy\itshape {translit}}})")
        lines.append(r"\\")
        lines.append(rf"{{\wordstudy\itshape {escape_latex(definition)}}}")
        lines.append("")

    lines.append(r"\restoregeometry")
    return lines


async def _render_commentary_appendix(
    main_passage: str,
    commentary_sources: list[str],
    preloaded: list[CommentaryResult] | None = None,
) -> list[str]:
    """Render commentary appendix section."""
    lines = []
    logger.info("Rendering commentary appendix for passage: %s, sources: %s", main_passage, commentary_sources)

    # Map source strings to CommentarySource enum
    slug_to_source = {s.value: s for s in CommentarySource}
    sources = [slug_to_source[src] for src in commentary_sources if src in slug_to_source]

    if preloaded is not None:
        commentaries = preloaded
    else:
        if not sources:
            logger.info("No valid commentary sources after mapping")
            return lines

        # Fetch commentary for the main passage from each source
        commentaries: list[CommentaryResult] = []
        for source in sources:
            logger.info("Fetching commentary from %s for %s", source.value, main_passage)
            result = await fetch_commentary_for_reference(main_passage, source)
            if result:
                logger.info("Got commentary result with %d entries", len(result.entries))
                commentaries.append(result)
            else:
                logger.warning("No commentary result from %s", source.value)

    if not commentaries:
        logger.info("No commentaries returned from any source")
        return lines

    # Add appendix section with wider margins and different font
    lines.append("")
    lines.append(r"\newpage")
    lines.append(r"\newgeometry{left=10mm,right=15mm,top=15mm,bottom=10mm}")
    lines.append(r"\section{Commentary}")
    lines.append(r"\commentaryfont\small")
    lines.append("")

    for commentary in commentaries:
        # Source name as subsection
        lines.append(rf"\subsection{{{escape_latex(commentary.source_name)}}}")
        lines.append("")

        # Render each entry
        for entry in commentary.entries:
            # Add verse reference if it's a specific verse
            if entry.verse_start == entry.verse_end:
                lines.append(rf"\textbf{{v. {entry.verse_start}}}")
            elif entry.verse_end:
                lines.append(rf"\textbf{{vv. {entry.verse_start}--{entry.verse_end}}}")
            lines.append("")

            # Add commentary text (escape LaTeX special chars)
            text = escape_latex(entry.text)
            # Convert double newlines to LaTeX paragraph breaks
            text = text.replace("\n\n", "\n\n\\medskip\n\n")
            lines.append(text)
            lines.append("")
            lines.append(r"\medskip")
            lines.append("")

    # Restore original geometry
    lines.append(r"\restoregeometry")
    return lines
