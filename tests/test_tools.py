"""Catalog, orders, identity and return rules. The critical guarantees of the project live here."""
from __future__ import annotations

import json
import time
from datetime import datetime

import pytest

# Order 1: customer 3, delivered, purchased 2025-10-15, estimated delivery 2025-10-25.
ORDER_1_EMAIL = "pedro.oliveira@jmail.com"
ORDER_1_PHONE = "(67) 98432-1098"


def _names(result: dict) -> set[str]:
    return {p["nome"] for p in result["produtos"]}


# Catalog


def test_budget_search_returns_exactly_the_sellable_guitars(tools):
    result = tools.search_products(category="Violões", max_price=1000)
    assert result["total_encontrado"] == 12
    ids = {p["id"] for p in result["produtos"]}
    assert ids == {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112}
    assert 96 not in ids and 113 not in ids
    assert result["produtos"][0]["preco_atual"] == "R$ 429,90"  # cheapest first


def test_search_filters_by_promotional_price(tools):
    # Ohana CK-20 lists at R$ 549,00 but costs R$ 439,20 on promotion.
    assert "Ohana CK-20 Concert Natural" in _names(tools.search_products(category="Ukuleles", max_price=450))


def test_search_by_text_and_category_is_accent_insensitive(tools):
    assert tools.search_products(category="violoes", query="nylon", max_price=500)["total_encontrado"] == 2


def test_search_empty_category_reports_nothing_instead_of_inventing(tools):
    result = tools.search_products(category="Instrumentos de Sopro (Madeiras)")
    assert result["status"] == "nenhum_produto_encontrado" and result["produtos"] == []


def test_unknown_category_lists_valid_ones(tools):
    result = tools.search_products(category="Amplificadores")
    assert result["status"] == "categoria_inexistente" and "Violões" in result["categorias"]


@pytest.mark.parametrize("query", ["Takamine GD20", "takamine gd-20", "gd20", "TAKAMINE GD 20"])
def test_get_product_finds_customer_spellings(tools, query):
    result = tools.get_product(query)
    assert result["produtos"][0]["id"] == 95
    assert result["produtos"][0]["preco_atual"] == "R$ 2.199,00"


def test_ambiguous_name_returns_both_models(tools):
    assert {p["id"] for p in tools.get_product("Martin D-28")["produtos"]} == {93, 108}


def test_expired_promotion_is_labelled_and_never_applied(tools):
    product = tools.get_product("Tagima Woodstock")["produtos"][0]
    assert product["preco_atual"] == "R$ 899,00" and product["em_promocao"] is False
    assert {"nome": "Black Friday", "desconto": "30%"} in product["promocoes_encerradas"]


def test_active_promotion_is_applied(tools):
    product = tools.get_product("Ohana CK-20")["produtos"][0]
    assert product["preco_atual"] == "R$ 439,20" and product["promocao"]["desconto"] == "20%"


@pytest.mark.parametrize(
    "query, label",
    [
        ("Giannini GF-3D", "temporariamente indisponível"),
        ("Shelby SN-7C", "não faz mais parte do catálogo"),
        ("Ibanez Bass 2X", "não faz mais parte do catálogo"),
        ("Kala KA-ABP-CTG", "ainda não lançado, indisponível para compra"),
    ],
)
def test_unsellable_products_have_alternatives_and_no_stock_count(tools, query, label):
    product = tools.get_product(query)["produtos"][0]
    assert product["disponibilidade"] == label
    assert "unidades_em_estoque" not in product
    alternatives = product["alternativas_disponiveis"]
    assert alternatives and all(a["disponibilidade"] == "disponível" for a in alternatives)


def test_record_conflict_hides_description(tools):
    product = tools.get_product("Music Man Bass 1X")["produtos"][0]
    assert "alerta_cadastro" in product and "descricao" not in product


def test_unknown_product_is_not_found(tools):
    assert tools.get_product("Stradivarius Messiah")["status"] == "produto_nao_encontrado"


def test_active_promotions_list_is_sellable_and_active_only(tools):
    assert {p["id"] for p in tools.list_active_promotions()["produtos"]} == {90, 94, 121, 127}


def test_consultations_are_fast(tools):
    started = time.perf_counter()
    tools.search_products(category="Violões", max_price=1000)
    tools.get_product("Takamine GD20")
    tools.get_policy(["4"])
    assert (time.perf_counter() - started) / 3 < 0.05


# Identity


def test_order_number_alone_discloses_nothing(tools):
    result = tools.get_my_orders(order_id=1)
    assert result["status"] == "verificacao_necessaria" and "pedidos" not in result


def test_email_alone_without_order_number_discloses_nothing(tools):
    assert tools.get_my_orders(email=ORDER_1_EMAIL)["status"] == "verificacao_necessaria"


def test_incomplete_requests_do_not_count_as_failures(tools):
    for _ in range(5):
        tools.get_my_orders(order_id=1)
    assert tools.get_my_orders(order_id=1, email=ORDER_1_EMAIL)["status"] == "ok"


def test_order_with_email_on_file(tools):
    result = tools.get_my_orders(order_id=1, email=" Pedro.Oliveira@JMAIL.com ")
    assert result["status"] == "ok" and result["primeiro_nome"] == "Pedro"
    assert result["pedidos"][0]["codigo_de_rastreamento"] == "BRAB1234567BR"


@pytest.mark.parametrize("phone", ["(67) 98432-1098", "67984321098", "+55 67 98432-1098", "984321098"])
def test_order_with_phone_in_customer_formats(tools, phone):
    assert tools.get_my_orders(order_id=1, phone=phone)["status"] == "ok"


def test_email_and_phone_without_order_number_lists_only_own_orders(tools):
    result = tools.get_my_orders(email=ORDER_1_EMAIL, phone=ORDER_1_PHONE)
    assert {o["numero_pedido"] for o in result["pedidos"]} == {1, 19}


def test_shared_email_is_separated_by_phone(tools):
    # Customers 11 and 43 share an email in the records. Only customer 11 has orders.
    assert tools.get_my_orders(email="bruno.martins@jmail.com", phone="(67) 99456-3456")["pedidos"] == []
    orders = tools.get_my_orders(email="bruno.martins@jmail.com", phone="(67) 98543-2109")["pedidos"]
    assert [o["numero_pedido"] for o in orders] == [10]


def test_failure_is_identical_for_existing_and_missing_orders(make_tools):
    wrong_owner = make_tools(session_id="a").get_my_orders(order_id=1, email="ana.costa@hayoo.com.br")
    missing = make_tools(session_id="b").get_my_orders(order_id=999, email="ana.costa@hayoo.com.br")
    assert wrong_owner == missing
    assert wrong_owner["status"] == "verificacao_falhou"


def test_mismatched_second_factor_fails(tools):
    assert tools.get_my_orders(order_id=1, email=ORDER_1_EMAIL, phone="(67) 90000-0000")["status"] == "verificacao_falhou"


def test_lockout_blocks_correct_data_after_three_failures(tools):
    assert tools.get_my_orders(order_id=1, email="x@x.com")["status"] == "verificacao_falhou"
    assert tools.get_my_orders(order_id=1, email="y@x.com")["status"] == "verificacao_falhou"
    assert tools.get_my_orders(order_id=1, email="z@x.com")["status"] == "verificacao_bloqueada"
    result = tools.get_my_orders(order_id=1, email=ORDER_1_EMAIL)
    assert result["status"] == "verificacao_bloqueada" and "pedidos" not in result


def test_lockout_persists_across_turns(tools, storage):
    for attempt in "abc":
        tools.get_my_orders(order_id=1, email=f"{attempt}@x.com")
    reloaded = storage.load_session("s1", "fake", "fake-model")
    assert reloaded.failed_verifications == 3


def test_return_assessment_requires_verification(tools):
    assert tools.check_return_eligibility(order_id=1, reason="arrependimento", email="x@x.com")["status"] == "verificacao_falhou"
    assert "elegivel" not in tools.check_return_eligibility(order_id=1, reason="arrependimento")


def test_no_tool_output_contains_contact_data(data, tools):
    # A verified customer's own email and phone never return, nor do those of anyone else.
    outputs = [
        tools.get_my_orders(order_id=o.id, email=data.customers[o.customer_id].email) for o in data.orders.values()
    ]
    outputs += [tools.search_products(), tools.list_active_promotions(), tools.get_product("Yamaha")]
    text = json.dumps(outputs, ensure_ascii=False)
    for customer in data.customers.values():
        assert customer.email not in text
        assert customer.phone not in text
        assert customer.name not in text


def test_past_due_shipped_order_gets_alert(make_tools):
    before = make_tools(datetime(2026, 2, 20, 10, 0)).get_my_orders(order_id=8, email="anacarol.ferreira@coldmail.com")
    assert "alerta" not in before["pedidos"][0]
    after = make_tools(datetime(2026, 3, 5, 10, 0)).get_my_orders(order_id=8, email="anacarol.ferreira@coldmail.com")
    assert "alerta" in after["pedidos"][0]


def test_total_mismatch_is_flagged(tools):
    result = tools.get_my_orders(order_id=3, email="isabela.moreira@jmail.com")
    assert "alerta_total" in result["pedidos"][0] and result["pedidos"][0]["total"] == "R$ 3.450,00"


# Returns. Order 7: customer 14, delivered, purchased 2026-02-03, estimated delivery 2026-02-17.

ORDER_7 = dict(order_id=7, email="leticia.rocha@jmail.com")


def _assess(make_tools, now: datetime, reason: str, **order) -> dict:
    return make_tools(now).check_return_eligibility(reason=reason, **(order or ORDER_7))


@pytest.mark.parametrize(
    "now, eligible",
    [(datetime(2026, 2, 20, 10, 0), True), (datetime(2026, 2, 24, 23, 0), True), (datetime(2026, 2, 25, 9, 0), False)],
)
def test_regret_window_is_seven_days_after_receipt(make_tools, now, eligible):
    result = _assess(make_tools, now, "arrependimento")
    assert result["elegivel"] is eligible and result["prazo_final"] == "24/02/2026"


def test_regret_within_window_states_conditions_and_assumptions(make_tools):
    result = _assess(make_tools, datetime(2026, 2, 20, 10, 0), "arrependimento")
    conditions = " ".join(result["condicoes"])
    assert "10 dias úteis" in conditions and "frete de devolução" in conditions
    assumptions = " ".join(result["premissas"])
    assert "data real de recebimento" in assumptions and "canal da compra" in assumptions


def test_preference_window(make_tools):
    assert _assess(make_tools, datetime(2026, 2, 24, 10, 0), "preferencia")["elegivel"] is True
    assert _assess(make_tools, datetime(2026, 2, 25, 10, 0), "preferencia")["elegivel"] is False


def test_defect_exchange_counts_from_purchase(make_tools):
    # Purchase on 2026-02-03: 30 days end on 2026-03-05.
    inside = _assess(make_tools, datetime(2026, 3, 5, 10, 0), "defeito")
    assert inside["elegivel"] is True and inside["troca_na_loja_ate"] == "05/03/2026"
    outside = _assess(make_tools, datetime(2026, 3, 6, 10, 0), "defeito")
    assert outside["elegivel"] is False and "fabricante" in outside["proximo_passo"]


def test_legal_warranty_counts_from_receipt(make_tools):
    # Receipt on 2026-02-17: 90 days end on 2026-05-18.
    assert _assess(make_tools, datetime(2026, 5, 18, 10, 0), "defeito")["dentro_da_garantia_legal"] is True
    assert _assess(make_tools, datetime(2026, 5, 19, 10, 0), "defeito")["dentro_da_garantia_legal"] is False


@pytest.mark.parametrize(
    "order_id, email, fragment",
    [
        (8, "anacarol.ferreira@coldmail.com", "em transporte"),
        (9, "juliana.almeida@hayoo.com.br", "ainda não foi despachado"),
        (13, "fernanda.ribeiro@coldmail.com", "ainda não foi despachado"),
        (17, "matheus.correia@hayoo.com.br", "cancelado"),
    ],
)
@pytest.mark.parametrize("reason", ["arrependimento", "defeito", "preferencia"])
def test_orders_not_delivered_are_not_eligible(make_tools, order_id, email, fragment, reason):
    result = make_tools().check_return_eligibility(order_id=order_id, email=email, reason=reason)
    assert result["elegivel"] is False and fragment in result["explicacao"]


def test_invalid_reason_is_rejected(tools):
    result = tools.check_return_eligibility(reason="troco", **ORDER_7)
    assert result["status"] == "motivo_invalido"


# Tickets


def test_complaint_ticket_has_protocol_and_deadline(tools, storage):
    result = tools.register_ticket("reclamacao", "Produto chegou riscado", "Ana", "ana@x.com")
    assert result["protocolo"] == "EM-20260210-0001" and result["prazo_de_retorno"] == "24 horas úteis"
    assert storage.tickets()[0]["summary"] == "Produto chegou riscado"
    assert "loja_reabre" not in result


def test_ticket_outside_hours_states_reopening(make_tools):
    result = make_tools(datetime(2026, 10, 31, 14, 0)).register_ticket("encaminhamento", "Quer falar com uma pessoa")
    assert result["loja_reabre"] == "03/11/2026 às 09:00" and "prazo_de_retorno" not in result


def test_protocols_are_sequential(tools):
    assert tools.register_ticket("encaminhamento", "a")["protocolo"].endswith("0001")
    assert tools.register_ticket("encaminhamento", "b")["protocolo"].endswith("0002")


def test_invalid_ticket_kind_is_rejected(tools):
    assert tools.register_ticket("spam", "x")["status"] == "tipo_invalido"
