"""Generate LaTeX from parsed sermon outline."""
import logging

from .models import SermonOutline, SermonPoint, SermonSubPoint
from .commentary import CommentarySource, fetch_commentary_for_reference, CommentaryResult

logger = logging.getLogger(__name__)


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
\usepackage[protrusion=true,expansion=true,tracking=true,kerning=true,spacing=true]{microtype}

% PDF metadata / links
\usepackage{hyperref}

% Pandoc list helper
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}%
}

% Two-column scripture + bullets
\newcommand{\scripturebullets}[2]{%
  \begin{samepage}
  \noindent
  \begin{minipage}[t]{0.50\textwidth}
    #1
  \end{minipage}\hfill
  \begin{minipage}[t]{0.50\textwidth}
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

    lines.append(rf"\section{{{escape_latex(point.title)}}}")
    lines.append("")

    if point.content:
        lines.append(escape_latex(point.content))
        lines.append("")

    # Sub-points as subsections with scripturebullets
    for sub in point.sub_points:
        lines.extend(_render_subpoint(sub, version))

    lines.append(r"\newpage{}")
    lines.append("")

    return lines


def _render_subpoint(sub: SermonSubPoint, version: str) -> list[str]:
    """Render a sub-point with scripture on left, bullets on right."""
    lines = []

    title = escape_latex(sub.title) if sub.title else ""
    lines.append(rf"\subsection{{{title}}}")
    lines.append("")

    # Build scripture side
    scripture_lines = []
    if sub.scripture_verse:
        scripture_lines.append(scripture_placeholder(sub.scripture_verse, version))
    scripture_lines.append(r"\vspace{2.2in}")
    scripture_content = "\n".join(scripture_lines)

    # Build bullets side
    bullet_lines = []
    bullets = sub.bullets if sub.bullets else []
    # If no bullets but content exists, use content as a single bullet
    if not bullets and sub.content:
        bullets = [sub.content]

    if bullets:
        bullet_lines.append(r"\begin{itemize}")
        bullet_lines.append(r"\tightlist")
        for bullet in bullets:
            bullet_lines.append(rf"\item {escape_latex(bullet)}\\")
        bullet_lines.append(r"\end{itemize}")
    bullet_lines.append(r"\vspace{2.2in}")
    bullets_content = "\n".join(bullet_lines)

    # Combine with scripturebullets
    lines.append(r"\scripturebullets")
    lines.append(r"{%")
    lines.append(scripture_content)
    lines.append(r"}%")
    lines.append(r"{%")
    lines.append(bullets_content)
    lines.append(r"}%")
    lines.append("")

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
