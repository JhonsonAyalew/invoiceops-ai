from datetime import date
from decimal import Decimal as D
import pytest
from app.extraction.numbers import parse_amount, parse_date, infer_decimal_separator


@pytest.mark.parametrize(
    "s,exp",
    [
        ("1,234.56", D("1234.56")),
        ("1.234,56", D("1234.56")),
        ("1 234,56", D("1234.56")),
        ("1'234.50", D("1234.50")),
        ("$12.50", D("12.50")),
        ("12,5", D("12.5")),
        ("0,15 €", D("0.15")),
        ("(12.00)", D("-12.00")),
        ("1,234,567.89", D("1234567.89")),
        ("1.234.567,89", D("1234567.89")),
        ("0.00", D("0.00")),
        ("1.000", D("1000")),
        ("abc", None),
    ],
)
def test_parse_amount(s, exp):
    assert parse_amount(s) == exp


def test_decimal_hint_resolves_ambiguity():
    assert parse_amount("1.234", ",") == D("1234")
    assert parse_amount("1.234", ".") == D("1.234")
    assert parse_amount("1,234", ",") == D("1.234")


def test_unit_price_not_float():
    assert isinstance(parse_amount("0,15"), D)
    assert parse_amount("0.1") + parse_amount("0.2") == D("0.3")


def test_infer_separator():
    assert infer_decimal_separator("Total 1.234,56 and 12,50") == ","
    assert infer_decimal_separator("Total 1,234.56 and 12.50") == "."


@pytest.mark.parametrize(
    "s,df,exp,amb",
    [
        ("2024-03-05", None, date(2024, 3, 5), False),
        ("15.03.2024", None, date(2024, 3, 15), False),
        ("03/15/2024", None, date(2024, 3, 15), False),
        ("03/04/2024", True, date(2024, 4, 3), False),
        ("03/04/2024", False, date(2024, 3, 4), False),
        ("03/04/2024", None, date(2024, 4, 3), True),
        ("March 3, 2024", None, date(2024, 3, 3), False),
        ("3 März 2024", None, date(2024, 3, 3), False),
        ("31/02/2024", None, None, False),
    ],
)
def test_parse_date(s, df, exp, amb):
    assert parse_date(s, df) == (exp, amb)
