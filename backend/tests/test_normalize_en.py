import pytest

from app.text.normalize import normalize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("$1,234.56", "one thousand, two hundred and thirty-four dollars, fifty-six cents"),
        ("Chapter XIV", "Chapter fourteen"),
        ("1939-1945", "nineteen thirty-nine to nineteen forty-five"),
        ("1939–1945", "nineteen thirty-nine to nineteen forty-five"),  # en-dash
        ("3rd", "third"),
        ("Dr. Smith vs. Mr. Jones", "Doctor Smith versus Mister Jones"),
        ("It cost $5.", "It cost five dollars."),
        ("45% of the people agreed.", "forty-five percent of the people agreed."),
        ("In 1905, the town was founded.", "In nineteen oh five, the town was founded."),
        ("The year 2024 was eventful.", "The year two thousand twenty-four was eventful."),
        ("In the year 2000, everything changed.", "In the year two thousand, everything changed."),
        ("She was born in 1800.", "She was born in eighteen hundred."),
        ("It was the 21st century.", "It was the twenty-first century."),
        (
            "There were 12,345 people in the crowd.",
            "There were twelve thousand, three hundred and forty-five people in the crowd.",
        ),
        ("Chapter IX: The Return", "Chapter nine: The Return"),
        ("He ran 3.14 miles.", "He ran three point one four miles."),
        ("Room & Board", "Room and Board"),
    ],
)
def test_normalize_en_golden(text, expected):
    assert normalize(text, "en") == expected


def test_allcaps_emphasis_title_cased_but_acronyms_kept():
    result = normalize("He shouted NEVER AGAIN while the NASA engineer watched.", "en")
    assert "Never Again" in result
    assert "NASA" in result


def test_smart_quotes_and_ellipsis_normalized():
    result = normalize("“Hello,” she said… ‘quietly.’", "en")
    assert result == '"Hello," she said... \'quietly.\''


def test_currency_symbols_gbp_eur():
    assert normalize("It cost £10.", "en") == "It cost ten pounds sterling."
    assert normalize("It cost €10.", "en") == "It cost ten euro."


def test_currency_zero_minor_unit_stripped_regardless_of_unit_name():
    # GBP's minor unit is "pence", not "cents" — the stripping must not be USD-specific.
    assert "pence" not in normalize("It cost £10.", "en")
