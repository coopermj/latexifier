"""Offline Hebrew corpus, English versification and strict passage coverage."""
import importlib.util
import re
import unicodedata
from pathlib import Path

import pytest


def test_hebrew_data_module_exists():
    assert importlib.util.find_spec('app.hebrew_interlinear') is not None


@pytest.fixture
def hebrew():
    from app import hebrew_interlinear
    return hebrew_interlinear


def unpointed(text):
    return ''.join(char for char in text if not unicodedata.combining(char))


def test_genesis_first_verse_has_seven_words_in_source_order(hebrew):
    words = hebrew.get_hebrew_passage_words('Genesis 1:1')
    assert len(words) == 7
    assert unpointed(words[0]['hebrew']) == 'בראשית'
    assert words[0]['strongs'] == 'H7225G'
    assert words[0]['gloss'] == 'in/ beginning'
    assert words[1]['gloss'] == 'he created'
    assert words[1]['lemma'] == 'בָּרָא'
    assert all(w['chapter'] == 1 and w['verse'] == 1 and w['language'] == 'hebrew' for w in words)
    assert all('/' not in w['hebrew'] and '\\' not in w['hebrew'] for w in words)


@pytest.mark.parametrize('reference', ['Gen 1:1', 'gen. 1:1', 'GENESIS 1:1'])
def test_canonical_and_source_book_aliases(hebrew, reference):
    assert hebrew.get_hebrew_passage_words(reference) == hebrew.get_hebrew_passage_words('Genesis 1:1')


def test_chapter_and_cross_chapter_ranges(hebrew):
    words = hebrew.get_hebrew_passage_words('Genesis 1')
    assert {w['verse'] for w in words} == set(range(1, 32))
    words = hebrew.get_hebrew_passage_words('Genesis 1:31–2:3')
    assert list(dict.fromkeys((w['chapter'], w['verse']) for w in words)) == [(1, 31), (2, 1), (2, 2), (2, 3)]


@pytest.mark.parametrize('reference', ['John 1:1', 'Genesis 1:31-32', 'Genesis 1:32-2:1', 'Genesis 1:3-2', 'Genesis 2:1-1:3', 'Genesis 0:1', 'Genesis 51', 'Genesis 1:0', 'Genesis 1:1-999999999', 'Genesis 1:1-999999999:1', '../Gen 1:1', '', 'Genesis 1:1,3'])
def test_invalid_and_partial_ranges_return_none(hebrew, reference):
    assert hebrew.get_hebrew_passage_words(reference) is None


def test_psalms_english_numbering_and_titles(hebrew):
    words = hebrew.get_hebrew_passage_words('Psalm 3:1')
    assert words[0]['gloss'] == 'O Yahweh'  # Hebrew 3:2, not its superscription.
    whole = hebrew.get_hebrew_passage_words('Psalms 3')
    assert whole[0]['verse'] == 0 and whole[0]['gloss'] == 'a psalm'
    assert max(w['verse'] for w in whole) == 8
    assert hebrew.get_hebrew_passage_words('Psalms 3:0')


def test_english_malachi_and_joel_chapter_mapping(hebrew):
    assert hebrew.get_hebrew_passage_words('Malachi 4:6')[0]['gloss'] == 'and/ he will turn back'
    assert hebrew.get_hebrew_passage_words('Joel 2:28')
    assert hebrew.get_hebrew_passage_words('Joel 4:1') is None


def test_aramaic_language_is_word_level(hebrew):
    words = hebrew.get_hebrew_passage_words('Daniel 2:4')
    assert [w['language'] for w in words[:5]] == ['hebrew'] * 4 + ['aramaic']
    assert all(w['language'] == 'aramaic' for w in hebrew.get_hebrew_passage_words('Ezra 4:9'))


def test_qere_is_selected_without_duplicate_ketiv_or_reconstructed_lxx(hebrew):
    words = hebrew.get_hebrew_passage_words('Genesis 9:21')
    assert len(words) == 7
    assert unpointed(words[-1]['hebrew']) == 'אהלו׃'
    assert words[-1]['text_type'].startswith('Q')
    assert len(hebrew.get_hebrew_passage_words('Genesis 4:8')) == 14
    assert hebrew.get_hebrew_passage_words('Joshua 21:36-37')
    assert all(w['hebrew'] for w in hebrew.get_hebrew_passage_words('Ruth 3:12'))


def test_exact_extended_lexicon_and_broad_definition(hebrew):
    entry = hebrew.get_hebrew_lexicon_entry('H7225G')
    assert entry['hebrew'] == 'רֵאשִׁית'
    assert entry['translit'] and entry['gloss'] and entry['def']
    assert entry['definition_strongs'] == 'H7225'
    assert '<' not in entry['def'] and '>' not in entry['def']
    assert hebrew.get_hebrew_lexicon_entry('H0430G')['gloss'] != hebrew.get_hebrew_lexicon_entry('H0430H')['gloss']
    assert hebrew.get_hebrew_lexicon_entry('G7225') is None
    assert hebrew.get_hebrew_lexicon_entry('H99999999') is None


def test_results_cannot_mutate_cached_data(hebrew):
    words = hebrew.get_hebrew_passage_words('Genesis 1:1')
    words[0]['hebrew'] = 'broken'
    assert hebrew.get_hebrew_passage_words('Genesis 1:1')[0]['hebrew'] != 'broken'
    entry = hebrew.get_hebrew_lexicon_entry('H7225G')
    entry['def'] = 'broken'
    assert hebrew.get_hebrew_lexicon_entry('H7225G')['def'] != 'broken'


def test_missing_book_or_verse_falls_back_completely(hebrew, monkeypatch):
    monkeypatch.setattr(hebrew, '_load_book', lambda code: {'1': {'1': [['א', 'one', 'H1', 'HN', 'L']]}})
    assert hebrew.get_hebrew_passage_words('Genesis 1:1-2') is None
    assert hebrew.get_hebrew_passage_words('Genesis 2:1') is None


def test_all_ot_books_and_every_token_have_lexicon_entries(hebrew):
    assert len(hebrew.BOOK_CODES) == 39
    total_words = 0
    for book, code in hebrew.BOOK_CODES.items():
        data = hebrew._load_book(code)
        assert data and hebrew.get_hebrew_passage_words(f'{book} 1:1')
        for chapter, verses in data.items():
            assert set(range(1, max(map(int, verses)) + 1)) <= set(map(int, verses))
            for words in verses.values():
                total_words += len(words)
                for word in words:
                    assert re.fullmatch(r'H\d{4}[A-Za-z]*', word[2])
                    assert hebrew.get_hebrew_lexicon_entry(word[2])
    assert total_words > 300_000


@pytest.mark.parametrize('bad_token', [None, ['א'], ['א', 'one', 'H0001', 'HN', None], ['א', 'one', 'G0001', 'HN', 'L']])
def test_malformed_book_tokens_fail_closed(hebrew, monkeypatch, tmp_path, bad_token):
    import gzip
    import json
    (tmp_path / 'Gen.json.gz').write_bytes(gzip.compress(json.dumps({'1': {'1': [bad_token]}}).encode()))
    monkeypatch.setattr(hebrew, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(hebrew, '_load_manifest', lambda: {'books': {'Gen': {'verse_word_counts': {'1': {'1': 1}}}}})
    hebrew._load_book.cache_clear()
    try:
        assert hebrew.get_hebrew_passage_words('Genesis 1:1') is None
    finally:
        hebrew._load_book.cache_clear()


def test_truncated_chapter_fails_closed(hebrew, monkeypatch, tmp_path):
    import gzip
    import json
    (tmp_path / 'Gen.json.gz').write_bytes(gzip.compress(json.dumps({'1': {'1': [['א', 'one', 'H0001', 'HN', 'L']]}}).encode()))
    monkeypatch.setattr(hebrew, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(hebrew, '_load_manifest', lambda: {'books': {'Gen': {'verse_word_counts': {'1': {'1': 2}}}}})
    hebrew._load_book.cache_clear()
    try:
        assert hebrew.get_hebrew_passage_words('Genesis 1') is None
    finally:
        hebrew._load_book.cache_clear()


def test_lexicon_build_excludes_restricted_meanings_and_xml_lists(tmp_path):
    from scripts.prepare_hebrew import load_lexicon, load_strongs
    source = tmp_path / 'strong.xml'
    source.write_text('''<osis xmlns="http://www.bibletechnologies.net/2003/OSIS/namespace">
      <div type="entry" n="1"><w lemma="אָב" xlit="av"/>
      <list><item>DO NOT INCLUDE BDB LIST</item></list>
      <note type="explanation"><hi>father</hi>, ancestor</note>
      <note type="translation">father</note></div></osis>''', encoding='utf-8')
    broad = load_strongs(source)
    assert broad['H0001']['def'] == 'father, ancestor'
    source = tmp_path / 'step.tsv'
    source.write_text('H0001\tH0001G =\tH0001G\tאָב\tav\tH:N-M\tfather\tDO NOT INCLUDE RESTRICTED MEANING\n', encoding='utf-8')
    lexicon = load_lexicon(source, broad)
    assert lexicon['H0001G']['def'] == 'father, ancestor'
    assert lexicon['H0001G']['gloss'] == 'father'
    assert 'DO NOT INCLUDE' not in repr(lexicon)


def test_compression_is_deterministic_without_file_or_time_metadata():
    import gzip
    from scripts.prepare_hebrew import compressed
    first = compressed({'verse': ['א', 'ב']})
    second = compressed({'verse': ['א', 'ב']})
    assert first == second
    assert first[3:8] == b'\x00' * 5
    assert gzip.decompress(first).decode() == '{"verse":["א","ב"]}\n'


@pytest.mark.parametrize('data', [[], {'H0001': []}, {'H0001': {'hebrew': None}}])
def test_malformed_lexicon_falls_back(hebrew, monkeypatch, tmp_path, data):
    import gzip
    import json
    (tmp_path / 'lexicon.json.gz').write_bytes(gzip.compress(json.dumps(data).encode()))
    monkeypatch.setattr(hebrew, '_DATA_DIR', tmp_path)
    hebrew._load_lexicon.cache_clear()
    try:
        assert hebrew.get_hebrew_lexicon_entry('H0001') is None
    finally:
        hebrew._load_lexicon.cache_clear()


def test_excessively_long_numeric_reference_is_rejected(hebrew):
    assert hebrew.get_hebrew_passage_words('Genesis ' + '1' * 5000 + ':1') is None


def test_invalid_deflate_falls_back(hebrew, monkeypatch, tmp_path):
    import gzip
    # Reserved DEFLATE block type: gzip's header is valid but zlib rejects it.
    payload = gzip.compress(b'{}')[:10] + b'\x07' + b'\x00' * 8
    (tmp_path / 'Gen.json.gz').write_bytes(payload)
    (tmp_path / 'lexicon.json.gz').write_bytes(payload)
    monkeypatch.setattr(hebrew, '_DATA_DIR', tmp_path)
    hebrew._load_book.cache_clear()
    hebrew._load_lexicon.cache_clear()
    try:
        assert hebrew.get_hebrew_passage_words('Genesis 1:1') is None
        assert hebrew.get_hebrew_lexicon_entry('H0001') is None
    finally:
        hebrew._load_book.cache_clear()
        hebrew._load_lexicon.cache_clear()
