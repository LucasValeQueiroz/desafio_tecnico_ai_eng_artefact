"""Read-only view of the store's records, loaded from CSV and normalized once at startup."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

CSV_PREFIX = "desafio_tecnico_ai_eng - "

IN_STOCK = "in_stock"
OUT_OF_STOCK = "out_of_stock"
DISCONTINUED = "discontinued"
COMING_SOON = "coming_soon"

# Brands and model lines used to spot a description that contradicts a product's name.
BRAND_MARKERS = {
    "crafter": ["crafter"],
    "fender": ["fender", "jazz bass", "precision"],
    "giannini": ["giannini"],
    "gibson": ["gibson"],
    "ibanez": ["ibanez"],
    "kala": ["kala"],
    "kalani": ["kalani"],
    "korg": ["korg"],
    "martin": ["martin"],
    "music man": ["music man", "stingray"],
    "nord": ["nord"],
    "ohana": ["ohana"],
    "pearl": ["pearl"],
    "prs": ["prs"],
    "roland": ["roland"],
    "rozini": ["rozini"],
    "shelby": ["shelby"],
    "takamine": ["takamine"],
    "tagima": ["tagima"],
    "tama": ["tama"],
    "taylor": ["taylor"],
    "yamaha": ["yamaha"],
}


def fold(text: str) -> str:
    """Lowercase and remove accents, for matching customers' spelling."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _brands_in(text: str) -> set[str]:
    folded = fold(text)
    return {
        brand
        for brand, markers in BRAND_MARKERS.items()
        if any(re.search(rf"\b{re.escape(marker)}\b", folded) for marker in markers)
    }


def _has_record_conflict(name: str, description: str) -> bool:
    name_brands = _brands_in(name)
    return bool(name_brands) and bool(_brands_in(description) - name_brands)


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    category_name: str
    description: str
    price: Decimal
    stock: int
    status: str
    specs: dict
    record_conflict: bool

    @property
    def availability(self) -> str:
        # Status wins over stock: a discontinued or unreleased product can't be sold even with units.
        if self.status == "discontinued":
            return DISCONTINUED
        if self.status == "coming_soon":
            return COMING_SOON
        return IN_STOCK if self.stock > 0 else OUT_OF_STOCK

    @property
    def sellable(self) -> bool:
        return self.availability == IN_STOCK


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    discount_percent: int
    description: str
    active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str

    @property
    def first_name(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    order_date: date
    status: str
    total: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    lines: tuple[OrderLine, ...]


def _rows(data_dir: Path, table: str) -> list[dict]:
    with (data_dir / f"{CSV_PREFIX}{table}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


class StoreData:
    def __init__(self, data_dir: Path) -> None:
        self.categories = {int(r["category_id"]): r["name"] for r in _rows(data_dir, "categories")}
        self.products = {
            int(r["product_id"]): Product(
                id=int(r["product_id"]),
                name=r["name"].strip(),
                category_id=int(r["category_id"]),
                category_name=self.categories[int(r["category_id"])],
                description=r["description"].strip(),
                price=Decimal(r["price_brl"]),
                stock=int(r["stock_quantity"]),
                status=r["status"].strip(),
                specs=json.loads(r["specs"]),
                record_conflict=_has_record_conflict(r["name"], r["description"]),
            )
            for r in _rows(data_dir, "products")
        }
        self.promotions = [
            Promotion(
                id=int(r["promotion_id"]),
                product_id=int(r["product_id"]),
                discount_percent=int(r["discount_percent"]),
                description=r["description"].strip(),
                active=r["is_active"].strip() == "1",
            )
            for r in _rows(data_dir, "promotions")
        ]
        self.customers = {
            int(r["customer_id"]): Customer(
                id=int(r["customer_id"]),
                name=r["name"].strip(),
                phone=r["phone"].strip(),
                email=r["email"].strip(),
                city=r["city"].strip(),
            )
            for r in _rows(data_dir, "customers")
        }
        lines: dict[int, list[OrderLine]] = {}
        for r in _rows(data_dir, "order_items"):
            lines.setdefault(int(r["order_id"]), []).append(
                OrderLine(product_id=int(r["product_id"]), quantity=int(r["quantity"]))
            )
        self.orders = {
            int(r["order_id"]): Order(
                id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                order_date=date.fromisoformat(r["order_date"]),
                status=r["status"].strip(),
                total=Decimal(r["total_brl"]),
                payment_method=r["payment_method"].strip(),
                tracking_code=r["tracking_code"].strip() or None,
                estimated_delivery=_optional_date(r["estimated_delivery"].strip()),
                notes=r["notes"].strip() or None,
                lines=tuple(lines.get(int(r["order_id"]), ())),
            )
            for r in _rows(data_dir, "orders")
        }

    def promotions_for(self, product_id: int) -> list[Promotion]:
        return [p for p in self.promotions if p.product_id == product_id]

    def active_promotion(self, product_id: int) -> Promotion | None:
        active = [p for p in self.promotions_for(product_id) if p.active]
        return max(active, key=lambda p: p.discount_percent, default=None)

    def order_total_from_lines(self, order: Order) -> Decimal:
        return sum((self.products[l.product_id].price * l.quantity for l in order.lines), Decimal(0))
