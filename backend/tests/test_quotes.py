import pytest

from app.quotes import normalize, verify_quote

SOURCE = (
    "The Great Wall is not visible from low Earth orbit with the naked eye, "
    "according to NASA astronauts. It is very long but quite narrow."
)


def test_exact_match():
    assert verify_quote(
        "The Great Wall is not visible from low Earth orbit with the naked eye", SOURCE
    )


@pytest.mark.parametrize(
    "quote",
    [
        "the great wall is NOT visible from low earth orbit",  # case
        "The  Great   Wall is not\nvisible from low Earth orbit",  # extra spaces
        "according to NASA astronauts. It is very long",  # punctuation kept
        "according to NASA astronauts It is very long",  # punctuation dropped
        "Great Wall is not visible from low Earth orbit!!",  # extra punctuation
    ],
)
def test_normalized_differences_pass(quote):
    assert verify_quote(quote, SOURCE)


def test_curly_quotes():
    source = "The minister said it’s “clearly the largest project in the country’s history”."
    quote = "it's \"clearly the largest project in the country's history\""
    assert verify_quote(quote, source)


def test_paraphrase_fails():
    assert not verify_quote("Astronauts say the Great Wall cannot be seen from orbit", SOURCE)


def test_under_six_words_fails():
    assert not verify_quote("The Great Wall is", SOURCE)
    assert not verify_quote("", SOURCE)


def test_normalize():
    assert normalize("  Hello,   “World”! ") == "hello world"
