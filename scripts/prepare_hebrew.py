#!/usr/bin/env python3
"""Rebuild bundled OT data from pinned, SHA-256-checked upstream sources.

Requires only Python's standard library. Downloads occur only with --download;
normal rebuilds use --source-dir. See docs/hebrew-data.md.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.hebrew_interlinear import BOOK_CODES

STEP_COMMIT = 'ae39711d7843b2902d54993e432de9c12d6a4b9a'
STRONG_COMMIT = '0acd2f251c2d35ff8db2dece4e0593979d3ac223'
TAHOT_SUFFIX = ' - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt'
TBESH_NAME = 'TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt'
SOURCE_SPECS = [
    ('Translators Amalgamated OT+NT/TAHOT Gen-Deu' + TAHOT_SUFFIX, 'e9b8546ee48fe0bfc57c3b70f5f40e98d96580e803526d19026224e31753368b'),
    ('Translators Amalgamated OT+NT/TAHOT Jos-Est' + TAHOT_SUFFIX, '195fee1dc3653bab33701f170734eb894ed647c10cd08cc61749375fe8b73775'),
    ('Translators Amalgamated OT+NT/TAHOT Job-Sng' + TAHOT_SUFFIX, '84e118a97e5725e3847cdfdd593873513021c790c63cc91a0d41fca2b5db2ed5'),
    ('Translators Amalgamated OT+NT/TAHOT Isa-Mal' + TAHOT_SUFFIX, 'f3ded203d2a74d6368932c97ae550d1d0754b271af491dc0dedf36fe3ba0bcc5'),
    ('Lexicons/' + TBESH_NAME, '464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591'),
]
SOURCES = [dict(filename=Path(path).name, sha256=sha,
                url=f'https://raw.githubusercontent.com/STEPBible/STEPBible-Data/{STEP_COMMIT}/' + urllib.parse.quote(path))
           for path, sha in SOURCE_SPECS]
SOURCES.append(dict(filename='StrongHebrewG.xml', sha256='1f9659ea208f4c498843a0280dacb1448627c33ca77712642d8705793ab66061',
                    url=f'https://raw.githubusercontent.com/openscriptures/strongs/{STRONG_COMMIT}/hebrew/StrongHebrewG.xml'))
ROW_RE = re.compile(r'^(\w{3})\.(\d+)\.(\d+)(?:\([^)]*\))?#[\d\w+.-]+=(.+)$')
ROOT_RE = re.compile(r'\{(H\d{4}[A-Za-z]*)')
STRONG_RE = re.compile(r'H\d{4}[A-Za-z]*')
NS = {'o': 'http://www.bibletechnologies.net/2003/OSIS/namespace'}


def normalized_text(value):
    return ' '.join(value.split())


def xml_text(element):
    """Retain references represented by empty source word elements, never HTML."""
    if element is None:
        return ''
    pieces = [element.text or '']
    for child in element:
        if child.tag.endswith('}w') and child.get('src'):
            pieces.append('H' + child.get('src'))
        else:
            pieces.append(xml_text(child))
        pieces.append(child.tail or '')
    return normalized_text(''.join(pieces))


def load_strongs(path):
    """Extract original Strong notes, never the separate BDB-style list nodes."""
    entries = {}
    for div in ET.parse(path).findall('.//o:div[@type="entry"]', NS):
        word = div.find('o:w', NS)
        identifier = f"H{int(div.attrib['n']):04d}"
        explanation = xml_text(div.find('o:note[@type="explanation"]', NS))
        translation = xml_text(div.find('o:note[@type="translation"]', NS))
        entries[identifier] = {'hebrew': word.get('lemma', ''), 'translit': word.get('xlit', ''),
                               'gloss': translation, 'def': explanation or translation,
                               'definition_strongs': identifier}
    return entries


def load_lexicon(path, broad):
    lexicon = {key: dict(value) for key, value in broad.items()}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        fields = line.split('\t')
        if len(fields) < 8 or not STRONG_RE.fullmatch(fields[0]):
            continue
        match = STRONG_RE.match(fields[1])
        if not match:
            raise ValueError('Unrecognized TBESH identifier: ' + fields[1])
        identifier = match[0]
        definition = broad.get(identifier[:5], {})
        # TBESH Meaning (column 8) is deliberately never read or redistributed.
        lexicon[identifier] = {'hebrew': fields[3], 'translit': fields[4], 'gloss': fields[6],
                               'def': definition.get('def', ''),
                               'definition_strongs': definition.get('definition_strongs', '')}
    return lexicon


def build(source_dir):
    broad = load_strongs(source_dir / 'StrongHebrewG.xml')
    lexicon = load_lexicon(source_dir / TBESH_NAME, broad)
    books = {code: {} for code in BOOK_CODES.values()}
    omitted = {'reconstructed_lxx_words': 0, 'qere_omissions': 0}
    supplemented = set()
    seen = set()
    for source in SOURCES[:4]:
        for line in (source_dir / source['filename']).read_text(encoding='utf-8-sig').splitlines():
            fields = line.split('\t')
            match = ROW_RE.fullmatch(fields[0])
            if not match:
                if re.match(r'^\w{3}\.\d+\.\d+', fields[0]):
                    raise ValueError('Unparsed source reference: ' + fields[0])
                continue
            code, chapter, verse, text_type = match.groups()
            if fields[0] in seen:
                raise ValueError('Duplicate source row: ' + fields[0])
            seen.add(fields[0])
            if text_type.startswith('X'):
                omitted['reconstructed_lxx_words'] += 1
                continue
            if not fields[1]:
                if not text_type.startswith('Q'):
                    raise ValueError('Unexpected empty Hebrew: ' + fields[0])
                omitted['qere_omissions'] += 1
                continue
            root = ROOT_RE.search(fields[4])
            if root is None or not fields[5].startswith(('H', 'A')):
                raise ValueError('Missing root/morphology: ' + fields[0])
            strongs = root[1]
            if strongs not in lexicon:
                # TAHOT and TBESH occasionally differ in disambiguated inventory.
                # Preserve TAHOT's exact tag, root form and root gloss.
                expanded = re.search(r'\{' + re.escape(strongs) + r'=([^=]+)=([^}]+)', fields[11])
                if not expanded:
                    raise ValueError('Missing lexicon/root expansion: ' + fields[0])
                definition = broad.get(strongs[:5], {})
                lexicon[strongs] = {'hebrew': expanded[1], 'translit': definition.get('translit', ''),
                                   'gloss': expanded[2], 'def': definition.get('def', ''),
                                   'definition_strongs': definition.get('definition_strongs', '')}
                supplemented.add(strongs)
            hebrew = fields[1].replace('/', '').replace('\\', '')
            token = [hebrew, fields[3], strongs, fields[5], text_type]
            books[code].setdefault(str(int(chapter)), {}).setdefault(str(int(verse)), []).append(token)
    for code, chapters in books.items():
        if not chapters or set(map(int, chapters)) != set(range(1, max(map(int, chapters)) + 1)):
            raise ValueError('Incomplete chapters: ' + code)
        for chapter, verses in chapters.items():
            if not set(range(1, max(map(int, verses)) + 1)) <= set(map(int, verses)):
                raise ValueError(f'Incomplete verses: {code}.{chapter}')
    return books, lexicon, omitted, sorted(supplemented)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def compressed(value):
    buffer = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=buffer, mode='wb', compresslevel=9, mtime=0) as stream:
        stream.write(json_bytes(value))
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'app/data/hebrew')
    parser.add_argument('--download', action='store_true', help='Download missing pinned sources')
    args = parser.parse_args()
    args.source_dir.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        path = args.source_dir / source['filename']
        if not path.exists() and args.download:
            with urllib.request.urlopen(source['url'], timeout=60) as response:
                path.write_bytes(response.read())
        if not path.exists():
            parser.error(f'Missing {path}; provide source cache or use --download')
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            parser.error(f'SHA-256 mismatch: {path}')
    books, lexicon, omitted, supplemented = build(args.source_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'format_version': 1, 'sources': SOURCES, 'step_commit': STEP_COMMIT,
                'strongs_commit': STRONG_COMMIT, 'versification': 'English (NRSV), Psalm titles at verse 0',
                'token_fields': ['hebrew', 'gloss', 'strongs', 'morph', 'text_type'],
                'omitted': omitted, 'tahot_lexicon_supplements': supplemented, 'books': {}}
    for code, chapters in books.items():
        payload = compressed(chapters)
        (args.output_dir / f'{code}.json.gz').write_bytes(payload)
        counts = {ch: {verse: len(words) for verse, words in verses.items()} for ch, verses in chapters.items()}
        manifest['books'][code] = {'verse_word_counts': counts, 'sha256': hashlib.sha256(payload).hexdigest()}
    payload = compressed(lexicon)
    (args.output_dir / 'lexicon.json.gz').write_bytes(payload)
    manifest['lexicon'] = {'entries': len(lexicon), 'sha256': hashlib.sha256(payload).hexdigest()}
    (args.output_dir / 'manifest.json').write_bytes(json_bytes(manifest))
    print(f'Built {len(books)} books, {sum(len(w) for b in books.values() for ch in b.values() for w in ch.values()):,} words, {len(lexicon):,} lexicon entries.')


if __name__ == '__main__':
    main()
