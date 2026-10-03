import pytest
from unittest.mock import patch

SAMPLE_BEREAN = {
    "Ephesians": {
        "4": {
            "22": [
                {"greek": "ἀποθέσθαι", "lemma": "ἀποτίθημι", "strongs": "659", "gloss": "to put off", "morph": "V-AMN"},
                {"greek": "ὑμᾶς", "lemma": "σύ", "strongs": "5209", "gloss": "you", "morph": "P-2AP"},
            ],
            "23": [
                {"greek": "ἀνανεοῦσθαι", "lemma": "ἀνανεόω", "strongs": "365", "gloss": "to be renewed", "morph": "V-PPN"},
            ],
        }
    }
}


def test_is_nt_passage_ephesians():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("Ephesians 4:22-25") is True


def test_is_nt_passage_genesis():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("Genesis 1:1") is False


def test_is_nt_passage_1_corinthians():
    from app.interlinear import is_nt_passage
    assert is_nt_passage("1 Corinthians 13:4") is True


def test_get_passage_words_single_verse():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        words = get_passage_words("Ephesians 4:22")
    assert words is not None
    assert len(words) == 2
    assert words[0]["greek"] == "ἀποθέσθαι"
    assert words[0]["verse"] == 22


def test_get_passage_words_range():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        words = get_passage_words("Ephesians 4:22-23")
    assert words is not None
    assert len(words) == 3
    assert words[2]["verse"] == 23


def test_get_passage_words_ot_returns_none():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        result = get_passage_words("Genesis 1:1")
    assert result is None


def test_get_passage_words_missing_reference_returns_none():
    from app.interlinear import get_passage_words
    with patch("app.interlinear._load_berean", return_value=SAMPLE_BEREAN):
        result = get_passage_words("Ephesians 99:1")
    assert result is None


@pytest.mark.parametrize("reference", ["Romans 1-2", "Romans 1–2"])
def test_whole_chapter_range_matches_explicit_range(reference):
    from app.interlinear import get_passage_words, is_nt_passage
    assert is_nt_passage(reference)
    assert get_passage_words(reference) == get_passage_words("Romans 1:1-2:29")


def test_en_dash_verse_range():
    from app.interlinear import get_passage_words
    assert get_passage_words("Romans 1:1–7") == get_passage_words("Romans 1:1-7")


@pytest.mark.parametrize("reference", ["Romans 2-1", "Romans 16-17", "Isaiah 3-4"])
def test_invalid_or_non_nt_chapter_ranges_return_none(reference):
    from app.interlinear import get_passage_words
    assert get_passage_words(reference) is None
