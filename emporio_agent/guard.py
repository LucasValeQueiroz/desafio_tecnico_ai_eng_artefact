"""Safety net: every amount and percentage in a reply must be traceable to known evidence (RF-24)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MONEY = re.compile(r"R\$\s*(\d[\d.,]*\d|\d)", re.IGNORECASE)
PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
BARE_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def parse_amount(raw: str) -> Decimal | None:
    """Read Brazilian and plain numeric formats: 2.199,00 / 2199,00 / 2199.90 / 1.000 / 1000."""
    raw = raw.strip()
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        normalized = raw.replace(".", "")
    else:
        normalized = raw
    try:
        return Decimal(normalized).normalize()
    except InvalidOperation:
        return None


@dataclass
class Evidence:
    """Amounts and percentages seen in tool results and in the customer's own words."""

    amounts: set[str] = field(default_factory=set)
    percents: set[str] = field(default_factory=set)

    def _add(self, regex: re.Pattern, text: str, target: set[str]) -> None:
        for match in regex.finditer(text):
            raw = match.group(1) if regex.groups else match.group(0)
            value = parse_amount(raw)
            if value is not None:
                target.add(str(value))

    def add_trusted_text(self, text: str) -> None:
        self._add(MONEY, text, self.amounts)
        self._add(PERCENT, text, self.percents)

    def add_customer_text(self, text: str) -> None:
        # Customers write budgets without a currency sign ("até 1000"), so any number counts.
        self._add(BARE_NUMBER, text, self.amounts)
        self._add(PERCENT, text, self.percents)

    def to_json(self) -> dict:
        return {"amounts": sorted(self.amounts), "percents": sorted(self.percents)}

    @classmethod
    def from_json(cls, data: dict) -> "Evidence":
        return cls(set(data.get("amounts", [])), set(data.get("percents", [])))


def find_untraceable(reply: str, evidence: Evidence) -> list[str]:
    """Return the amounts and percentages in a reply that no evidence supports."""
    problems = []
    for match in MONEY.finditer(reply):
        value = parse_amount(match.group(1))
        if value is None or str(value) not in evidence.amounts:
            problems.append(match.group(0))
    for match in PERCENT.finditer(reply):
        value = parse_amount(match.group(1))
        if value is None or str(value) not in evidence.percents:
            problems.append(match.group(0))
    return problems
