import pytest

from app.text.normalize import normalize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Kapitel XIV", "Kapitel vierzehn"),
        ("1939-1945", "neunzehnhundertneununddreißig bis neunzehnhundertfünfundvierzig"),
        ("Im Jahr 1939 begann der Krieg.", "Im Jahr neunzehnhundertneununddreißig begann der Krieg."),
        ("Das war im Jahr 2024.", "Das war im Jahr zweitausendvierundzwanzig."),
        ("Das kostete 5 €.", "Das kostete fünf Euro."),
        ("Das kostete 12,50 €.", "Das kostete zwölf Euro und fünfzig Cent."),
        ("Er hatte 45% Chance.", "Er hatte fünfundvierzig Prozent Chance."),
        ("Nr. 5 war die Antwort.", "Nummer fünf war die Antwort."),
        ("Die Zahl 12.345 Einwohner.", "Die Zahl zwölftausenddreihundertfünfundvierzig Einwohner."),
    ],
)
def test_normalize_de_golden(text, expected):
    assert normalize(text, "de") == expected


def test_abbreviations_expand_correctly():
    result = normalize("Das war z.B. so, bzw. anders, usw.", "de")
    assert "zum Beispiel" in result
    assert "beziehungsweise" in result
    assert "und so weiter" in result


def test_abbreviation_preserves_sentence_initial_capitalization():
    assert normalize("Z.B. so.", "de") == "Zum Beispiel so."


def test_ordinal_period_only_fires_in_known_context():
    # "3. Kapitel" is an ordinal marker; an ordinary sentence-ending number followed
    # by a new capitalized sentence must NOT be misread as one.
    assert normalize("3. Kapitel", "de") == "dritte Kapitel"
    result = normalize("Es war 1999. Der Mann ging.", "de")
    assert "dritte" not in result
    assert "neunzehnhundertneunundneunzig" in result


def test_eur_currency_dollar_and_pound_prefix_use_english_number_format():
    # $ / £ amounts keep comma-thousands/period-decimal formatting even in German
    # text (regression: this previously broke on "$1,234.56", misreading the comma
    # as a German decimal mark and leaving the rest of the number un-narrated).
    result = normalize("Das kostete $1,234.56.", "de")
    assert "eintausendzweihundertvierunddreißig Dollar und sechsundfünfzig Cent" in result
    assert "$" not in result


def test_eur_symbol_matches_without_a_word_boundary_bug():
    # Regression: a trailing \b immediately after the "€" symbol never matches (\b
    # only fires at a word/non-word transition, and symbol-then-punctuation is
    # non-word-to-non-word), which silently left "12,50 €" completely unconverted.
    result = normalize("Es kostete 12,50 €.", "de")
    assert "€" not in result
    assert "Komma" not in result  # would indicate the decimal regex caught it instead


def test_known_declension_limitation_documented_by_this_test():
    # "3. Kapitel" grammatically wants "drittes" (strong neuter nominative) and "am
    # 3. Mai" wants "dritten" (weak masculine dative) — num2words has no gender/case
    # parameter, so both get the same citation form "dritte". Intelligible, not
    # grammatically perfect; see the module docstring. This test exists so a future
    # change to this behavior is a deliberate decision, not a silent regression.
    assert normalize("3. Kapitel", "de") == "dritte Kapitel"
    assert normalize("Am 3. Mai geschah es.", "de") == "Am dritte Mai geschah es."


def test_smart_quotes_normalized():
    assert normalize("„Hallo,” sagte sie… 'leise.'", "de") == '"Hallo," sagte sie... \'leise.\''


def test_allcaps_emphasis_title_cased_but_acronym_kept():
    result = normalize("Er schrie NIEMALS WIEDER während die USA zusahen.", "de")
    assert "Niemals Wieder" in result
    assert "USA" in result
