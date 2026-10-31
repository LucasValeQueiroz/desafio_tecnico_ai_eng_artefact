"""Convert the store manual PDF into a reviewable, section-addressable Markdown file.

Run once when the manual changes, then review the diff:

    python scripts/build_policy_kb.py
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "políticas_da_loja.pdf"
TARGET = ROOT / "emporio_agent" / "knowledge" / "policies.md"

PAGE_FURNITURE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")
HEADING = re.compile(r"^(\d+(?:\.\d+)?)\.? (.+)$")
LIST_ITEM = re.compile(r"^\d+\. ")
NOTE_PREFIX ="> **Nota de conciliação (não consta no manual original):** "

# Human-reviewed resolutions for places where the manual contradicts itself or the records.
# Each one is an assumption documented in the spec and in the README.
RECONCILIATION = {
    "1": "O manual cita mais de 300 instrumentos e categorias como sopros e cordas orquestrais. O que pode ser vendido é somente o que consta no sistema: consulte sempre o catálogo.",
    "1.2": "O e-mail correto é contato@emporiodamusica.com.br, sem acento no domínio. O telefone e WhatsApp oficial é (67) 3341-4444.",
    "3": "A parcela mínima de R$ 100,00 desta tabela vale apenas para 7x a 12x. As regras detalhadas da seção 3.1 prevalecem por serem mais específicas.",
    "3.1": "Até 3x, a parcela não pode ficar abaixo de R$ 50,00. O limite de parcelas de cada produto já vem calculado pela consulta de produto.",
    "4.1": "O sistema não registra a data real de recebimento nem o canal da compra. A elegibilidade de cada pedido é calculada pela ferramenta de devolução, que informa essas premissas.",
    "4.2": "Esta troca em loja (30 dias após a compra) e a garantia legal da seção 8.1 (90 dias após o recebimento) são caminhos distintos e podem coexistir.",
    "4.3": "O manual não define o início dos 7 dias. Adotamos a data de recebimento, como no direito de arrependimento.",
    "7": "A seção 1.2 informa outro número. Use sempre (67) 3341-4444 como telefone e WhatsApp oficial.",
    "7.1": "O manual não lista lojas parceiras. Não indique nomes de lojas.",
}


def _body_size(lines: list[dict]) -> float:
    sizes = collections.Counter(round(c["size"], 1) for line in lines for c in line["chars"])
    return sizes.most_common(1)[0][0]


def _table_to_markdown(table: list[list[str | None]]) -> str:
    rows = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in table]
    header, *body = rows
    out = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    out += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(out)


def _page_blocks(page) -> list[tuple[float, str, str]]:
    """Return (vertical position, kind, text) blocks for a page, with tables as units."""
    tables = page.find_tables()
    blocks = [(t.bbox[1], "table", _table_to_markdown(t.extract())) for t in tables]
    lines = page.extract_text_lines(return_chars=True)
    body_size = _body_size(lines)
    previous_right_edge = 0.0
    for line in lines:
        if any(t.bbox[1] <= line["top"] <= t.bbox[3] for t in tables):
            continue
        text = line["text"].strip()
        if PAGE_FURNITURE.match(text):
            continue
        first = line["chars"][0]
        is_large = round(first["size"], 1) > body_size
        is_bold = "bold" in first["fontname"].lower()
        if is_large and HEADING.match(text):
            kind = "heading"
        elif text.startswith("•") or LIST_ITEM.match(text) or is_bold or previous_right_edge < page.width * 0.72:
            kind = "para"
        else:
            kind = "cont"
        blocks.append((line["top"], kind, text))
        previous_right_edge = line["x1"]
    return sorted(blocks, key=lambda b: b[0])


def build() -> str:
    out: list[str] = []
    with pdfplumber.open(SOURCE) as pdf:
        pages = pdf.pages[1:]  # The cover only repeats contact details.
        for page in pages:
            for _, kind, text in _page_blocks(page):
                if kind == "heading":
                    number, title = HEADING.match(text).groups()
                    level = "###" if "." in number else "##"
                    out.append(f"\n{level} {number} {title}\n")
                    if number in RECONCILIATION:
                        out.append(NOTE_PREFIX + RECONCILIATION[number] + "\n")
                elif kind == "table":
                    out.append("\n" + text + "\n")
                elif kind == "cont" and out:
                    out[-1] = out[-1].rstrip("\n") + " " + text
                else:
                    out.append(text)
    body = "\n".join(line for line in out if line.strip())
    return (
        "# Manual de Políticas e Procedimentos — Empório da Música\n\n"
        "Gerado por scripts/build_policy_kb.py a partir de data/políticas_da_loja.pdf (versão 2.1, junho de 2025).\n"
        + body.rstrip()
        + "\n"
    )


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(build(), encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
