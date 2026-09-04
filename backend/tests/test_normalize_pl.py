import pytest

from app.text.normalize import normalize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Rozdział XIV", "Rozdział czternasty"),
        ("Rozdział IX: Powrót", "Rozdział dziewiąty: Powrót"),
        ("1939-1945", "tysiąc dziewięćset trzydziesty dziewiąty do tysiąc dziewięćset czterdziesty piąty"),
        (
            "W 1939 roku wybuchła wojna.",
            "W tysiąc dziewięćset trzydziesty dziewiąty roku wybuchła wojna.",
        ),
        ("To było w roku 2024.", "To było w roku dwa tysiące dwudziesty czwarty."),
        ("To kosztowało 100 zł.", "To kosztowało sto złotych."),
        ("To kosztowało 12,50 zł.", "To kosztowało dwanaście złotych, pięćdziesiąt groszy."),
        ("Miał 45% szans.", "Miał czterdzieści pięć procent szans."),
        ("Liczba 12.345 mieszkańców.", "Liczba dwanaście tysięcy trzysta czterdzieści pięć mieszkańców."),
    ],
)
def test_normalize_pl_golden(text, expected):
    assert normalize(text, "pl") == expected


def test_abbreviation_preserves_sentence_initial_capitalization():
    assert normalize("Np. tak.", "pl") == "Na przykład tak."
    assert normalize("To jest np. przykład.", "pl") == "To jest na przykład przykład."


def test_abbreviations_expand_correctly():
    result = normalize("To np. tak, itd. i tzn. tamto, m.in. to.", "pl")
    assert "na przykład" in result
    assert "i tak dalej" in result
    assert "to znaczy" in result
    assert "między innymi" in result


def test_ul_abbreviation():
    assert normalize("ul. Kwiatowa 5", "pl") == "ulica Kwiatowa pięć"


def test_usd_currency_zero_cents_stripped():
    assert normalize("To kosztowało $5.", "pl") == "To kosztowało pięć dolarów amerykańskich."


def test_pln_currency_no_zero_grosze_suffix():
    result = normalize("To kosztowało 100 zł.", "pl")
    assert "zero groszy" not in result


def test_allcaps_emphasis_title_cased_but_acronym_kept():
    result = normalize("Krzyknął NIGDY WIĘCEJ podczas gdy USA patrzyło.", "pl")
    assert "Nigdy Więcej" in result
    assert "USA" in result


def test_smart_quotes_normalized():
    assert normalize("„Cześć,” powiedziała… 'cicho.'", "pl") == '"Cześć," powiedziała... \'cicho.\''
