from unittest.mock import patch

SAMPLE_LSJ = {
    "3056": {
        "lemma": "λόγος",
        "entry": "I. the word by which the inward thought is expressed. II. a saying, proverb, maxim."
    },
    "659": {
        "lemma": "ἀποτίθημι",
        "entry": "I. to put away or aside. II. mid., to lay aside for oneself."
    }
}


def test_get_lsj_entry_known():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value=SAMPLE_LSJ):
        result = get_lsj_entry("3056")
    assert result == "I. the word by which the inward thought is expressed. II. a saying, proverb, maxim."


def test_get_lsj_entry_unknown_returns_none():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value=SAMPLE_LSJ):
        result = get_lsj_entry("9999")
    assert result is None


def test_get_lsj_entry_empty_file_returns_none():
    from app.lsj import get_lsj_entry
    with patch("app.lsj._load_lsj", return_value={}):
        result = get_lsj_entry("3056")
    assert result is None
