from app.placeholders import _format_scripture_body


def test_net_prose_number_with_strongs_tag_is_not_treated_as_verse_number():
    text = (
        '<p class="bodytext">'
        '<span class="vref"><b>24:<span class="verseNumber">10</span></b></span> '
        "When the governor gestured for him to speak. "
        '<span class="vref"><b><span class="verseNumber">11</span></b></span> '
        'As you can verify for yourself, not more than <st data-num="1427" class="">12</st> '
        "days ago I went up to Jerusalem to worship. "
        '<span class="vref"><b><span class="verseNumber">12</span></b></span> '
        "They did not find me arguing with anyone."
        "</p>"
    )

    formatted = _format_scripture_body(
        "Acts 24:10-12",
        text,
        include_verse_numbers=True,
        include_footnotes=False,
        nolinks=True,
    )

    assert r"\vs{10}" in formatted
    assert r"\vs{11}" in formatted
    assert r"\vs{12} They did not find me" in formatted
    assert "not more than 12 days ago" in formatted
    assert r"not more than \vs{12} days ago" not in formatted


def test_bracketed_inline_verse_numbers_still_convert():
    formatted = _format_scripture_body(
        "Acts 24:11-12",
        "[11] As you can verify for yourself. [12] They did not find me arguing.",
        include_verse_numbers=True,
        include_footnotes=False,
    )

    assert r"\vs{11} As you can verify" in formatted
    assert r"\vs{12} They did not find" in formatted


def test_scripture_nested_single_quotes_become_typographic_quotes():
    formatted = _format_scripture_body(
        "Acts 26:14-15",
        (
            '[14] I heard a voice saying, "Saul, Saul, why are you persecuting me?" '
            "[15] And the Lord replied, 'I am Jesus whom you are persecuting.'"
        ),
        include_verse_numbers=True,
        include_footnotes=False,
    )

    assert (
        "\u201cSaul, Saul, why are you persecuting me?\u201d "
        "\\vs{15} And the Lord replied, "
        "\u2018I am Jesus whom you are persecuting.\u2019"
    ) in formatted
    assert "'I am Jesus" not in formatted


def test_scripture_apostrophes_stay_closing_quotes():
    formatted = _format_scripture_body(
        "Acts 26:15",
        "[15] Paul's defense doesn't fail, and the Jews' accusation won't stand.",
        include_verse_numbers=True,
        include_footnotes=False,
    )

    assert "Paul\u2019s defense doesn\u2019t fail" in formatted
    assert "Jews\u2019 accusation won\u2019t stand" in formatted
    assert "Paul\u2018s" not in formatted
    assert "doesn\u2018t" not in formatted
