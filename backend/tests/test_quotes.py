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


# ---- verify_quote and "[...]" gaps


def test_quote_across_gap_fails():
    source = "The wall is long and thin.\n[...]\nIt is not visible from orbit at all."
    assert not verify_quote("The wall is long and thin. It is not visible", source)
    assert verify_quote("It is not visible from orbit at all", source)


# ---- find_quote: recovery of near-miss quotes

PAGE = (
    "The Eiffel Tower is 330 metres (1,083 ft) tall, about the same height as an 81-storey "
    "building. It was completed in 1889 for the World's Fair. Sales fell by 20% in 2023, the "
    "company said. The wall isn't visible from the Moon. Some people believe the wall can be "
    "seen from orbit. In fact it can't be seen with the naked eye from low Earth orbit."
    "\n[...]\n"
    "For the record: no manmade structures on Earth can be seen with the"
    "\n[...]\n"
    "be seen with the unaided eye from the Moon, astronauts say."
)


@pytest.mark.parametrize(
    "quote, expected",
    [
        # exact words: the source's own text and punctuation come back, grown to the sentence
        ("It was completed in 1889 for the World's Fair",
         "It was completed in 1889 for the World's Fair."),
        ("sales fell by 20% in 2023", "Sales fell by 20% in 2023, the company said."),
        # number format
        ("The Eiffel Tower is 330 metres (1083 ft) tall",
         "The Eiffel Tower is 330 metres (1,083 ft) tall, about the same height as an "
         "81-storey building."),
        # "percent" for "%", a dropped "'s", a contraction spelled out, US spelling
        ("Sales fell by 20 percent in 2023, the company said.",
         "Sales fell by 20% in 2023, the company said."),
        ("It was completed in 1889 for the World Fair.",
         "It was completed in 1889 for the World's Fair."),
        ("The wall is not visible from the Moon.", "The wall isn't visible from the Moon."),
        ("The Eiffel Tower is 330 meters (1,083 ft) tall",
         "The Eiffel Tower is 330 metres (1,083 ft) tall, about the same height as an "
         "81-storey building."),
        # an added article
        ("In fact it can't be seen with the naked eye from the low Earth orbit.",
         "In fact it can't be seen with the naked eye from low Earth orbit."),
        # a quote with "..." keeps its longest real piece
        ("Some people believe ... in fact it can't be seen with the naked eye from low Earth orbit",
         "In fact it can't be seen with the naked eye from low Earth orbit."),
        # glued across a "[...]" gap: the piece that keeps the negation, within one passage
        ("No manmade structures on Earth can be seen with the unaided eye from the Moon",
         "For the record: no manmade structures on Earth can be seen with the"),
        # a short table row is fine when it has a number and matches exactly
        ("completed in 1889 for", "It was completed in 1889 for the World's Fair."),
    ],
)  # fmt: skip
def test_find_quote_recovers_source_text(quote, expected):
    from app.quotes import find_quote

    found = find_quote(quote, PAGE)
    assert found == expected
    assert verify_quote(found, PAGE)


@pytest.mark.parametrize(
    "quote",
    [
        "The Eiffel Tower is 300 metres (1,083 ft) tall",  # changed number
        "It was completed in 1899 for the World's Fair.",  # changed year
        "Sales fell by 2% in 2023, the company said.",
        "Sales rose by 20% in 2023, the company said.",  # changed verb
        "The wall is visible from the Moon.",  # negation dropped
        "In fact it can be seen with the naked eye from low Earth orbit.",
        "Some people believe the wall cannot be seen from orbit.",  # negation added
        "The Eiffel Tower is 330 metres tall, about the same height as an 81-storey building.",
        "In fact it can't be seen with the naked eye from high Earth orbit.",  # content word
        "Astronauts say the Great Wall cannot be seen from orbit",  # paraphrase
        "It was completed in 1889 for the Olympic Games.",
        "fell by 20%",  # too short
        "",
    ],
)
def test_find_quote_rejects_meaning_changes(quote):
    from app.quotes import find_quote

    assert find_quote(quote, PAGE) is None


def test_find_quote_never_runs_across_a_gap():
    from app.quotes import find_quote

    found = find_quote("can be seen with the be seen with the unaided eye", PAGE)
    assert found == "be seen with the unaided eye from the Moon, astronauts say."
    assert "[...]" not in (find_quote("no manmade structures on Earth can be seen", PAGE) or "")


def test_find_quote_spelling_variant_but_not_antonym():
    from app.quotes import find_quote

    source = "The new policy was careful and its colour scheme is bright and cheerful today."
    assert find_quote("The new policy was careful and its color scheme is bright", source)
    assert find_quote("The new policy was careless and its colour scheme is bright", source) is None
