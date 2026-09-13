"""Hebrew interlinear and lexicon layout for the sermon PDF."""
import re
import textwrap

from .hebrew_interlinear import get_hebrew_lexicon_entry


def _escape(text: str) -> str:
    # Import lazily: the sermon renderer also calls this module.
    from .sermon_latex import escape_latex
    return escape_latex(text)


def _mixed_text(text: str) -> str:
    """Keep Hebrew embedded in English definitions in its own direction/font."""
    return ''.join(
        rf'\hebrewtext{{{_escape(part)}}}' if re.search(r'[\u0590-\u05ff]', part)
        else _escape(part)
        for part in re.split(r'([\u0590-\u05ff]+(?:[ /-][\u0590-\u05ff]+)*)', text)
    )


def interlinear_label(words: list[dict]) -> str:
    languages = {word.get('language', 'hebrew') for word in words}
    if languages == {'aramaic'}:
        return 'Aramaic Interlinear'
    if 'aramaic' in languages:
        return 'Hebrew and Aramaic Interlinear'
    return 'Hebrew Interlinear'


def render_hebrew_interlinear(words: list[dict], reference: str, version: str) -> list[str]:
    from .sermon_latex import scripture_placeholder

    lines = [r'\newpage{}', r'\hypertarget{interlinear}{}',
             r'\columnratio{0.5}', r'\setlength{\columnsep}{1.5em}',
             r'\begin{paracol}{2}', r'\small\raggedright',
             rf'{{\josefin\textbf{{{interlinear_label(words)}}}}}\par',
             r'{\scripturefont\scriptsize Read Hebrew from right to left; glosses are word-level study aids.}\par']
    current = None
    for word in words:
        key = (word['chapter'], word['verse'])
        if key != current:
            if current is not None:
                lines.append(r'\end{hebrewverse}')
            lines.append(rf'\begin{{hebrewverse}}{{{key[0]}:{key[1]}}}')
            current = key
        # Wrap long phrases in the word stack, without reordering Hebrew units.
        gloss = r'\\'.join('{' + _escape(line) + '}' for line in textwrap.wrap(
            word.get('gloss', ''), width=18, break_long_words=False, break_on_hyphens=False))
        strongs = word.get('strongs', '')
        lines.append(rf'\hebrewintword{{{_escape(word["hebrew"])}}}{{{gloss}}}{{{strongs}}}')
    if current is not None:
        lines.append(r'\end{hebrewverse}')
    lines.extend([r'\par\switchcolumn', r'\pardir TLT\textdir TLT\raggedright',
                  scripture_placeholder(reference, version, nolinks=True),
                  r'\end{paracol}', r'\newpage{}'])
    return lines


def render_hebrew_lexicon(words: list[dict]) -> list[str]:
    identifiers = sorted({w['strongs'] for w in words if w.get('strongs')})
    if not identifiers:
        return []
    label = interlinear_label(words).replace('Interlinear', 'Lexicon')
    lines = [r'\newpage{}', r'\newgeometry{left=10mm,right=15mm,top=15mm,bottom=10mm}',
             r'\hypertarget{lexicon}{}', rf'\section{{{label}}}',
             r'\begingroup\scripturefont\small\raggedright',
             r'Hebrew and Aramaic text and word glosses: STEPBible / Tyndale House, CC BY 4.0. '
             r'Definitions: Strong\textquoteright s Hebrew dictionary (public domain), '
             r'via Open Scriptures.\par',
             r'\href{https://github.com/STEPBible/STEPBible-Data}{STEPBible source data}'
             r'\quad\href{https://github.com/openscriptures/strongs}{Strong\textquoteright s source data}\par']
    for identifier in identifiers:
        entry = get_hebrew_lexicon_entry(identifier)
        # A source gloss still gives a valid destination if a definition is absent.
        first = next(w for w in words if w.get('strongs') == identifier)
        entry = entry or {'hebrew': first.get('lemma', first['hebrew']), 'gloss': first.get('gloss', '')}
        lines.extend([
            r'\par\addvspace{10pt}\Needspace{5\baselineskip}',
            rf'\hypertarget{{lex-{identifier}}}{{}}',
            rf'{{\fontsize{{10}}{{12}}\selectfont\hebrewtext{{{_escape(entry.get("hebrew", ""))}}}}}\quad{{}}'
            rf'{_mixed_text(entry.get("translit", ""))}\hfill'
            rf'{{\addfontfeatures{{Numbers=Lining}}\textbf{{{identifier}}}}}\par',
            r'\nobreak\hrule\nobreak\vspace{4pt}',
            rf'\textbf{{{_mixed_text(entry.get("gloss", ""))}}}'
            + (' --- ' + _mixed_text(entry['def']) if entry.get('def') else '') + r'\par',
        ])
    lines.extend([r'\endgroup', r'\restoregeometry'])
    return lines
