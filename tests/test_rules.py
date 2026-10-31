"""Pricing, clock, records, manual sections and the safety net."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from emporio_agent.clock import StoreClock
from emporio_agent.guard import Evidence, find_untraceable, parse_amount
from emporio_agent.pricing import brl, max_installments, price_quote


@pytest.mark.parametrize(
    "value, expected",
    [("2199", "R$ 2.199,00"), ("799.9", "R$ 799,90"), ("12000", "R$ 12.000,00"), ("159.90", "R$ 159,90")],
)
def test_brl_format(value, expected):
    assert brl(Decimal(value)) == expected


def test_quote_without_promotion_offers_pix():
    quote = price_quote(Decimal("2199"))
    assert quote["preco_atual"] == "R$ 2.199,00"
    assert quote["preco_no_pix"] == "R$ 2.089,05"
    assert quote["em_promocao"] is False


def test_quote_with_promotion_shows_original_and_blocks_pix():
    quote = price_quote(Decimal("549"), 20, "Desconto Exclusivo")
    assert quote["preco_tabela"] == "R$ 549,00"
    assert quote["preco_atual"] == "R$ 439,20"
    assert quote["promocao"]["desconto"] == "20%"
    assert "preco_no_pix" not in quote


@pytest.mark.parametrize(
    "total, expected",
    [
        ("40", 1),        # below the minimum even for two installments
        ("120", 2),       # R$ 60 in 2x, R$ 40 in 3x is too low
        ("159.9", 3),     # 3x = 53,30; 4x would be under R$ 80
        ("320", 4),       # 4x = 80,00 exactly
        ("480", 6),       # 6x = 80,00 exactly
        ("699.9", 6),     # 7x would be 99,99, under R$ 100
        ("700", 7),       # 7x = 100,00 exactly
        ("1199", 11),     # 12x would be 99,92
        ("1200", 12),     # 12x = 100,00 exactly
        ("11499", 12),
    ],
)
def test_installment_limits(total, expected):
    assert max_installments(Decimal(total)) == expected


@pytest.mark.parametrize(
    "now, is_open",
    [
        (datetime(2026, 2, 10, 10, 30), True),   # Tuesday morning
        (datetime(2026, 2, 10, 18, 0), False),   # closes at 18:00
        (datetime(2026, 2, 7, 12, 59), True),    # Saturday before closing
        (datetime(2026, 2, 7, 13, 0), False),    # Saturday closes at 13:00
        (datetime(2026, 2, 8, 10, 0), False),    # Sunday
        (datetime(2026, 11, 2, 10, 0), False),   # Monday, national holiday
    ],
)
def test_opening_hours(now, is_open):
    assert StoreClock(now).is_open() is is_open


def test_next_opening_skips_sunday_and_holiday():
    clock = StoreClock(datetime(2026, 10, 31, 14, 0))
    assert clock.next_opening() == datetime(2026, 11, 3, 9, 0, tzinfo=clock.next_opening().tzinfo)
    line = clock.context_line()
    assert "fechada" in line and "terça-feira, 03/11/2026, às 09:00" in line


def test_next_opening_before_opening_is_same_day():
    clock = StoreClock(datetime(2026, 2, 10, 7, 0))
    assert clock.next_opening().day == 10


def test_sellability_follows_status_over_stock(data):
    assert data.products[130].availability == "coming_soon" and data.products[130].stock == 2
    assert data.products[136].availability == "discontinued" and data.products[136].stock == 13
    assert data.products[96].availability == "out_of_stock"
    assert data.products[95].sellable


def test_record_conflicts_are_exactly_the_mismatched_products(data):
    flagged = {p.id for p in data.products.values() if p.record_conflict}
    assert flagged == {135, 136, 137, 139, 140, 142, 144}


def test_all_csv_rows_load(data):
    assert len(data.products) == 65 and len(data.orders) == 20
    assert len(data.customers) == 50 and len(data.promotions) == 25


def test_only_active_promotions_are_returned(data):
    assert data.active_promotion(121).discount_percent == 20
    assert data.active_promotion(91) is None
    assert data.active_promotion(96) is None


def test_manual_has_every_numbered_section(policies):
    expected = {
        "1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5", "5.1", "5.2", "5.3",
        "6", "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8", "8.1", "8.2", "8.3", "9", "10",
    }
    assert set(policies.sections) == expected


def test_manual_section_contents_survive_extraction(policies):
    assert "Rua 14 de Maio, 3200" in policies.sections["1.2"].body
    assert "09:00 às 13:00" in policies.sections["2"].body
    assert "em até 10 dias úteis" in policies.sections["4.1"].body
    assert "3321-4500" in policies.sections["7"].body and "3341-4444" in policies.sections["7"].body
    assert "Página" not in "".join(s.body for s in policies.sections.values())


def test_top_level_section_includes_subsections(policies):
    result = policies.get(["4"])
    assert [s["secao"] for s in result["secoes"]] == ["4", "4.1", "4.2", "4.3", "4.4"]


def test_section_ten_does_not_match_section_one(policies):
    assert [s["secao"] for s in policies.get(["1"])["secoes"]] == ["1", "1.1", "1.2"]


def test_unknown_section_is_reported(policies):
    assert policies.get(["99"]) == {"secoes": [], "secoes_inexistentes": ["99"]}


@pytest.mark.parametrize(
    "raw, expected",
    [("2.199,00", "2199"), ("2199,00", "2199"), ("2199.90", "2199.9"), ("1.000", "1000"), ("1000", "1000"), ("799,9", "799.9")],
)
def test_amount_parsing(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


def test_guard_accepts_tool_values_in_other_formats():
    evidence = Evidence()
    evidence.add_trusted_text('{"preco": "R$ 2.199,00", "desconto": "5%"}')
    assert find_untraceable("Sai por R$ 2199,00, ou R$2.199,00, com 5% no PIX.", evidence) == []


def test_guard_flags_unknown_amount_and_percent():
    evidence = Evidence()
    evidence.add_trusted_text('{"preco": "R$ 2.199,00"}')
    assert find_untraceable("Faço por R$ 1.999,00 com 10% de desconto.", evidence) == ["R$ 1.999,00", "10%"]


def test_guard_accepts_customer_budget_without_currency_sign():
    evidence = Evidence()
    evidence.add_customer_text("tenho até 1000 reais")
    assert find_untraceable("Até R$ 1.000,00 tem bastante coisa!", evidence) == []


def test_customer_text_is_not_trusted_for_prices_it_did_not_state():
    evidence = Evidence()
    evidence.add_customer_text("me faz 50% de desconto?")
    assert find_untraceable("Não consigo dar 50%, mas o preço é R$ 100,00.", evidence) == ["R$ 100,00"]


def test_evidence_round_trip():
    evidence = Evidence()
    evidence.add_trusted_text("R$ 10,00 e 5%")
    assert Evidence.from_json(evidence.to_json()).to_json() == evidence.to_json()
