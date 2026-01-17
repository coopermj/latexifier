"""Generate LaTeX from parsed sermon outline."""
import json
import logging
from pathlib import Path

from .models import SermonOutline, SermonPoint, SermonSubPoint
from .commentary import CommentarySource, fetch_commentary_for_reference, CommentaryResult
from .scripture import fetch_scripture, ScriptureVersion, ScriptureLookupOptions

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


def scripture_placeholder(reference: str, version: str) -> str:
    """Generate a scripture placeholder string."""
    return f"[[scripture:{reference}|{version}]]"


def format_date(date_str: str | None) -> str:
    """Convert date to YYYY-MM-DD format if possible."""
    if not date_str:
        return ""
    # Try to parse common formats like "1/11/26" or "01/11/2026"
    import re
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
    if match:
        month, day, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return date_str


async def generate_sermon_latex(
    outline: SermonOutline,
    scripture_version: str = "ESV",
    subpoint_version: str = "NET",
    include_main_passage: bool = True,
    cover_image: str | None = None,
    commentary_sources: list[str] | None = None
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

    Returns:
        Complete LaTeX document as string
    """
    lines = []
    title = escape_latex(outline.metadata.title)
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

% Microtypography
\usepackage[protrusion=true,expansion=true,verbose=silent]{microtype}

% PDF metadata / links
\usepackage{hyperref}

% Pandoc list helper
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}%
}

% Two-column scripture + notes (with gutter)
\newcommand{\scripturebullets}[2]{%
  \begin{samepage}
  \noindent
  \begin{minipage}[t]{0.46\textwidth}
    #1
  \end{minipage}%
  \hspace{0.06\textwidth}%
  \begin{minipage}[t]{0.46\textwidth}
    #2
  \end{minipage}
  \end{samepage}
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

% Page number style
\fancypagestyle{mystyle}{%
  \fancyhf{}%
  \renewcommand\headrulewidth{0pt}%
  \fancyfoot[R]{\thepage}%
  \fancyfootoffset{2.1cm}%
}
\setlength{\footskip}{20pt}

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
    \qtcoronation{\@date}%
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
  pdfcreator={{LaTeX via pandoc}}
}}

\title{{{title}}}
\subtitle{{{main_passage_display}}}
\author{{{speaker}}}
\date{{{date}}}

\begin{{document}}
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

    lines.append("")
    lines.append(r"\newpage{}")
    lines.append("")

    # Main passage in two columns
    if include_main_passage and main_passage:
        lines.append(r"\begin{multicols}{2}")
        lines.append(scripture_placeholder(main_passage, scripture_version))
        lines.append(r"\end{multicols}")
        lines.append("")
        lines.append(r"\newpage{}")
        lines.append("")

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

    # Main points as sections
    for point in outline.points:
        lines.extend(_render_point(point, subpoint_version))

    # Greek Word Study appendix - fetch Strong's numbers from NET Bible
    strongs_numbers = set()
    if main_passage:
        try:
            net_result = await fetch_scripture(
                main_passage,
                ScriptureVersion.NET,
                ScriptureLookupOptions()
            )
            strongs_numbers = net_result.strongs_numbers
            logger.info("Extracted %d Strong's numbers from %s", len(strongs_numbers), main_passage)
        except Exception as e:
            logger.warning("Failed to fetch Strong's numbers for %s: %s", main_passage, e)

    if strongs_numbers:
        lines.extend(_render_word_study_from_strongs(strongs_numbers))

    # Commentary appendix
    if commentary_sources:
        commentary_lines = await _render_commentary_appendix(
            main_passage,
            commentary_sources
        )
        lines.extend(commentary_lines)

    lines.append(r"\end{document}")

    return "\n".join(lines)


def _render_point(point: SermonPoint, version: str) -> list[str]:
    """Render a main sermon point as a section."""
    lines = []
    section_title = escape_latex(point.title)

    # If point has sub-points, each sub-point gets its own page with section header
    if point.sub_points:
        for sub in point.sub_points:
            lines.extend(_render_subpoint(sub, version, section_title))
    else:
        # Point with no sub-points - render as full-width on its own page
        lines.append(r"\newpage{}")
        lines.append(rf"\section{{{section_title}}}")
        lines.append("")

        if point.content:
            lines.append(escape_latex(point.content))
            lines.append("")

        # Render bullets if present (simple bullet lists without letters)
        if point.bullets:
            lines.append(r"\begin{itemize}")
            lines.append(r"\setlength{\itemsep}{20pt}")
            for bullet in point.bullets:
                lines.append(rf"\item {escape_latex(bullet)}")
            lines.append(r"\end{itemize}")

        # Render numbered items if present (enumerated lists)
        if point.numbered_items:
            lines.append(r"\begin{enumerate}")
            lines.append(r"\setlength{\itemsep}{20pt}")
            for item in point.numbered_items:
                # Check if item has bold title pattern like "Title: explanation"
                if ": " in item:
                    parts = item.split(": ", 1)
                    lines.append(rf"\item \textbf{{{escape_latex(parts[0])}:}} {escape_latex(parts[1])}")
                else:
                    lines.append(rf"\item {escape_latex(item)}")
            lines.append(r"\end{enumerate}")

        # If there are scripture refs, render as list
        if point.scripture_refs:
            lines.append(r"\begin{itemize}")
            lines.append(r"\setlength{\itemsep}{20pt}")
            for ref in point.scripture_refs:
                lines.append(rf"\item {escape_latex(ref)}")
            lines.append(r"\end{itemize}")

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
        # Two-column layout: scripture on left, notes on right
        scripture_lines = []
        if sub.scripture_verse:
            scripture_lines.append(scripture_placeholder(sub.scripture_verse, version))
        if sub.scripture_refs:
            for ref in sub.scripture_refs:
                if scripture_lines:
                    scripture_lines.append("")
                    scripture_lines.append(r"\vspace{0.5cm}")
                    scripture_lines.append("")
                scripture_lines.append(scripture_placeholder(ref, version))
        scripture_lines.append(r"\vspace{2in}")
        scripture_content = "\n".join(scripture_lines)

        # Build notes side
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

        # Combine with scripturebullets
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
    lines.append(r"\newgeometry{left=20mm,right=25mm,top=15mm,bottom=15mm}")
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
        # Use wordstudy font for entire entry with itshape for italics
        lines.append(rf"{{\wordstudy\textbf{{G{num}}}}} --- {{\greekfont {greek}}} ({{\wordstudy\itshape {translit}}})")
        lines.append(r"\\")
        lines.append(rf"{{\wordstudy\itshape {escape_latex(definition)}}}")
        lines.append("")

    lines.append(r"\restoregeometry")
    return lines


async def _render_commentary_appendix(
    main_passage: str,
    commentary_sources: list[str]
) -> list[str]:
    """Render commentary appendix section."""
    lines = []
    logger.info("Rendering commentary appendix for passage: %s, sources: %s", main_passage, commentary_sources)

    # Map source strings to CommentarySource enum
    sources = []
    for src in commentary_sources:
        if src == "mhc":
            sources.append(CommentarySource.MHC)
        elif src == "calvincommentaries":
            sources.append(CommentarySource.CALVIN)

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
    lines.append(r"\newgeometry{left=20mm,right=25mm,top=15mm,bottom=15mm}")
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
