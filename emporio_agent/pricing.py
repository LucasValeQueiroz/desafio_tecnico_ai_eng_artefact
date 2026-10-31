"""Price rules from sections 3, 3.1 and 6.2 of the manual."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PIX_DISCOUNT_PERCENT = 5
MAX_INSTALLMENTS = 12


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def brl(value: Decimal) -> str:
    """Format as Brazilian currency, e.g. R$ 2.199,00."""
    formatted = f"{money(value):,.2f}"
    return "R$ " + formatted.replace(",", "§").replace(".", ",").replace("§", ".")


def apply_discount(price: Decimal, percent: int) -> Decimal:
    return money(price * (100 - percent) / 100)


def _minimum_installment(count: int) -> Decimal:
    if count <= 3:
        return Decimal(50)
    if count <= 6:
        return Decimal(80)
    return Decimal(100)


def max_installments(total: Decimal) -> int:
    """Largest interest-free installment count whose value respects the minimum for its range."""
    for count in range(MAX_INSTALLMENTS, 1, -1):
        if money(total / count) >= _minimum_installment(count):
            return count
    return 1


def price_quote(list_price: Decimal, promo_percent: int | None = None, promo_name: str | None = None) -> dict:
    """Everything the agent may say about a price, already calculated and formatted."""
    final = apply_discount(list_price, promo_percent) if promo_percent else money(list_price)
    count = max_installments(final)
    quote = {
        "preco_tabela": brl(list_price),
        "preco_atual": brl(final),
        "em_promocao": bool(promo_percent),
        "parcelamento_maximo_sem_juros": (
            f"{count}x de {brl(final / count)}" if count > 1 else "somente à vista"
        ),
    }
    if promo_percent:
        quote["promocao"] = {"nome": promo_name, "desconto": f"{promo_percent}%"}
        quote["pix"] = "O desconto de PIX não se aplica: preço já promocional e descontos não são cumulativos."
    else:
        quote["preco_no_pix"] = brl(apply_discount(list_price, PIX_DISCOUNT_PERCENT))
        quote["desconto_pix"] = f"{PIX_DISCOUNT_PERCENT}%"
    return quote
