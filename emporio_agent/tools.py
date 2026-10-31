"""Tools available to the model. Identity, prices and return windows are decided here, not in the prompt."""
from __future__ import annotations

import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from decimal import Decimal

from .clock import StoreClock
from .policies import PolicyBook
from .pricing import apply_discount, brl, price_quote
from .storage import SessionState, Storage
from .store_data import (
    COMING_SOON,
    DISCONTINUED,
    IN_STOCK,
    OUT_OF_STOCK,
    Customer,
    Order,
    Product,
    StoreData,
    fold,
)

MAX_FAILED_VERIFICATIONS = 3
SEARCH_LIMIT = 15
REGRET_DAYS = 7
PREFERENCE_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30
LEGAL_WARRANTY_DAYS = 90

AVAILABILITY_LABEL = {
    IN_STOCK: "disponível",
    OUT_OF_STOCK: "temporariamente indisponível",
    DISCONTINUED: "não faz mais parte do catálogo",
    COMING_SOON: "ainda não lançado, indisponível para compra",
}

ORDER_STATUS_LABEL = {
    "pending": "aguardando confirmação",
    "confirmed": "confirmado, em preparação (ainda não despachado)",
    "shipped": "despachado, em transporte",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAYMENT_LABEL = {
    "pix": "PIX",
    "boleto": "boleto bancário",
    "debit": "cartão de débito",
    "credit_3x": "cartão de crédito em 3x",
    "credit_6x": "cartão de crédito em 6x",
    "credit_12x": "cartão de crédito em 12x",
}

# Returned with product results, so that a purchase question doesn't need an extra consultation.
HOW_TO_BUY = (
    "Com a equipe pelo telefone ou WhatsApp (67) 3341-4444, pelo e-mail contato@emporiodamusica.com.br, "
    "ou na loja: Rua 14 de Maio, 3200 — Centro, Campo Grande - MS."
)

RECORD_CONFLICT_NOTE = (
    "O cadastro deste produto tem informações conflitantes entre nome e descrição. "
    "Informe apenas nome, preço e disponibilidade, e ofereça confirmar os detalhes técnicos com a equipe."
)

VERIFICATION_FAILED = {
    "status": "verificacao_falhou",
    "orientacao": "Não foi possível confirmar os dados informados. Peça para o cliente conferir o número do pedido e o e-mail ou telefone do cadastro.",
}
VERIFICATION_LOCKED = {
    "status": "verificacao_bloqueada",
    "orientacao": "Limite de tentativas atingido nesta conversa. Não tente novamente: registre um encaminhamento e direcione o cliente para a equipe.",
}
VERIFICATION_NEEDED = {
    "status": "verificacao_necessaria",
    "orientacao": "Para consultar um pedido, peça o número do pedido e o e-mail ou telefone do cadastro. Sem o número do pedido, peça o e-mail e o telefone do cadastro.",
}

TICKET_KINDS = ("reclamacao", "encaminhamento")
RETURN_REASONS = ("arrependimento", "defeito", "preferencia")


def _digits(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits[2:] if digits.startswith("55") and len(digits) > 11 else digits


def _same_phone(given: str, on_file: str) -> bool:
    given, on_file = _digits(given), _digits(on_file)
    # Customers often omit the area code, so nine digits may match the end of the number.
    return bool(given) and (given == on_file or (len(given) == 9 and on_file.endswith(given)))


def _same_email(given: str, on_file: str) -> bool:
    return given.strip().lower() == on_file.strip().lower()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _squeeze(text: str) -> str:
    return "".join(_tokens(text))


class StoreTools:
    def __init__(self, data: StoreData, policies: PolicyBook, clock: StoreClock, storage: Storage, session: SessionState) -> None:
        self._data = data
        self._policies = policies
        self._clock = clock
        self._storage = storage
        self._session = session
        self._handlers = {
            "search_products": self.search_products,
            "get_product": self.get_product,
            "list_active_promotions": self.list_active_promotions,
            "get_policy": self.get_policy,
            "get_my_orders": self.get_my_orders,
            "check_return_eligibility": self.check_return_eligibility,
            "register_ticket": self.register_ticket,
        }

    def execute(self, name: str, arguments: dict) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**arguments)

    # Catalog

    def _quote(self, product: Product) -> dict:
        promotion = self._data.active_promotion(product.id)
        if promotion:
            return price_quote(product.price, promotion.discount_percent, promotion.description)
        return price_quote(product.price)

    def _current_price(self, product: Product) -> Decimal:
        promotion = self._data.active_promotion(product.id)
        return apply_discount(product.price, promotion.discount_percent) if promotion else product.price

    def _summary(self, product: Product) -> dict:
        summary = {
            "id": product.id,
            "nome": product.name,
            "categoria": product.category_name,
            "disponibilidade": AVAILABILITY_LABEL[product.availability],
            **self._quote(product),
            "especificacoes": product.specs,
        }
        # Records are the only source for product details, so every result carries them.
        if product.record_conflict:
            summary["alerta_cadastro"] = RECORD_CONFLICT_NOTE
        else:
            summary["descricao"] = product.description
        if product.availability == IN_STOCK:
            summary["unidades_em_estoque"] = product.stock
        return summary

    def search_products(
        self,
        category: str | None = None,
        query: str | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
    ) -> dict:
        products = [p for p in self._data.products.values() if p.sellable]
        if category:
            wanted = fold(category)
            known = {fold(name) for name in self._data.categories.values()}
            if wanted not in known:
                return {"status": "categoria_inexistente", "categorias": sorted(self._data.categories.values())}
            products = [p for p in products if fold(p.category_name) == wanted]
        if max_price is not None:
            products = [p for p in products if self._current_price(p) <= Decimal(str(max_price))]
        if min_price is not None:
            products = [p for p in products if self._current_price(p) >= Decimal(str(min_price))]
        if query:
            products = self._filter_by_text(products, query)
        products.sort(key=self._current_price)
        return {
            "status": "ok" if products else "nenhum_produto_encontrado",
            "total_encontrado": len(products),
            "produtos": [self._summary(p) for p in products[:SEARCH_LIMIT]],
            "observacao": "Somente produtos disponíveis para compra. Filtros de preço usam o preço atual, antes do desconto de PIX.",
            "como_comprar": HOW_TO_BUY,
        }

    def _filter_by_text(self, products: list[Product], query: str) -> list[Product]:
        tokens = _tokens(query)

        def haystack(p: Product) -> str:
            specs = " ".join(str(v) for v in p.specs.values())
            return " ".join(_tokens(f"{p.name} {p.description} {specs} {p.category_name}"))

        return [p for p in products if all(t in haystack(p) for t in tokens)]

    def _match_by_name(self, query: str) -> list[Product]:
        tokens = _tokens(query)
        scored = []
        for product in self._data.products.values():
            name = _squeeze(product.name)
            overlap = sum(t in name for t in tokens) / len(tokens) if tokens else 0
            whole = 1.0 if _squeeze(query) and _squeeze(query) in name else 0
            similarity = SequenceMatcher(None, fold(query), fold(product.name)).ratio()
            scored.append((max(overlap, whole), similarity, product))
        best = max((s[0] for s in scored), default=0)
        if best >= 0.5:
            # Prefer products matching the most words; similarity separates close model names.
            top = sorted((s for s in scored if s[0] == best), key=lambda s: -s[1])
            return [s[2] for s in top[:3]]
        close = sorted((s for s in scored if s[1] >= 0.6), key=lambda s: -s[1])
        return [s[2] for s in close[:3]]

    def _alternatives(self, product: Product) -> list[dict]:
        def distance(candidate: Product) -> tuple:
            same_strings = candidate.specs.get("strings") == product.specs.get("strings")
            return (not same_strings, abs(candidate.price - product.price))

        peers = [
            p for p in self._data.products.values()
            if p.sellable and p.category_id == product.category_id and p.id != product.id
        ]
        return [self._summary(p) for p in sorted(peers, key=distance)[:3]]

    def get_product(self, query: str) -> dict:
        matches = self._match_by_name(query)
        if not matches:
            return {
                "status": "produto_nao_encontrado",
                "orientacao": "Este produto não consta no catálogo. Não presuma que ele existe; ofereça buscar opções na categoria.",
            }
        details = []
        for product in matches:
            item = self._summary(product)
            expired = [
                {"nome": p.description, "desconto": f"{p.discount_percent}%"}
                for p in self._data.promotions_for(product.id) if not p.active
            ]
            if expired:
                item["promocoes_encerradas"] = expired
            if not product.sellable:
                item["alternativas_disponiveis"] = self._alternatives(product)
            details.append(item)
        return {"status": "ok", "produtos": details, "como_comprar": HOW_TO_BUY}

    def list_active_promotions(self) -> dict:
        promoted = [
            self._data.products[p.product_id]
            for p in self._data.promotions
            if p.active and self._data.products[p.product_id].sellable
        ]
        return {"status": "ok", "produtos": [self._summary(p) for p in sorted(promoted, key=self._current_price)]}

    # Manual

    def get_policy(self, section_ids: list[str]) -> dict:
        return self._policies.get(section_ids)

    # Orders

    def _verify(self, order_id: int | None, email: str | None, phone: str | None) -> tuple[list[Order], Customer | None, dict | None]:
        """Return the orders a customer proved access to, or the refusal to send back."""
        if self._session.failed_verifications >= MAX_FAILED_VERIFICATIONS:
            return [], None, VERIFICATION_LOCKED

        factors = [f for f in (email, phone) if f and f.strip()]
        if not factors or (order_id is None and len(factors) < 2):
            return [], None, VERIFICATION_NEEDED

        def matches(customer: Customer) -> bool:
            return all(
                [
                    not (email and email.strip()) or _same_email(email, customer.email),
                    not (phone and phone.strip()) or _same_phone(phone, customer.phone),
                ]
            )

        if order_id is not None:
            order = self._data.orders.get(int(order_id))
            customer = self._data.customers.get(order.customer_id) if order else None
            if order and customer and matches(customer):
                return [order], customer, None
        else:
            customer = next((c for c in self._data.customers.values() if matches(c)), None)
            if customer:
                return [o for o in self._data.orders.values() if o.customer_id == customer.id], customer, None

        self._storage.record_failed_verification(self._session)
        if self._session.failed_verifications >= MAX_FAILED_VERIFICATIONS:
            return [], None, VERIFICATION_LOCKED
        return [], None, VERIFICATION_FAILED

    def _order_view(self, order: Order) -> dict:
        view = {
            "numero_pedido": order.id,
            "status": ORDER_STATUS_LABEL.get(order.status, order.status),
            "data_do_pedido": f"{order.order_date:%d/%m/%Y}",
            "itens": [
                {"produto": self._data.products[l.product_id].name, "quantidade": l.quantity} for l in order.lines
            ],
            "total": brl(order.total),
            "forma_de_pagamento": PAYMENT_LABEL.get(order.payment_method, order.payment_method),
            "codigo_de_rastreamento": order.tracking_code,
            "previsao_de_entrega": f"{order.estimated_delivery:%d/%m/%Y}" if order.estimated_delivery else None,
            "observacao_do_pedido": order.notes,
        }
        if order.status == "shipped" and order.estimated_delivery and order.estimated_delivery < self._clock.today():
            view["alerta"] = "A previsão de entrega já passou. Reconheça o atraso e ofereça encaminhar para a equipe."
        if self._data.order_total_from_lines(order) != order.total:
            view["alerta_total"] = "O total registrado difere da soma atual dos itens. Se o cliente questionar, encaminhe para a equipe."
        return view

    def get_my_orders(self, order_id: int | None = None, email: str | None = None, phone: str | None = None) -> dict:
        orders, customer, refusal = self._verify(order_id, email, phone)
        if refusal:
            return refusal
        return {"status": "ok", "primeiro_nome": customer.first_name, "pedidos": [self._order_view(o) for o in orders]}

    def check_return_eligibility(self, order_id: int, reason: str, email: str | None = None, phone: str | None = None) -> dict:
        orders, customer, refusal = self._verify(order_id, email, phone)
        if refusal:
            return refusal
        if reason not in RETURN_REASONS:
            return {"status": "motivo_invalido", "motivos_validos": list(RETURN_REASONS)}
        order = orders[0]
        result = {"status": "ok", "primeiro_nome": customer.first_name, "numero_pedido": order.id, "motivo": reason}
        return {**result, **self._assess_return(order, reason)}

    def _assess_return(self, order: Order, reason: str) -> dict:
        if order.status == "cancelled":
            return {"elegivel": False, "explicacao": "O pedido foi cancelado, então não há produto para devolver ou trocar."}
        if order.status in ("pending", "confirmed"):
            return {
                "elegivel": False,
                "explicacao": "O pedido ainda não foi despachado. O manual não trata de cancelamento antes do envio.",
                "proximo_passo": "Registrar encaminhamento para a equipe avaliar o pedido.",
            }
        if order.status == "shipped":
            return {
                "elegivel": False,
                "explicacao": "O pedido está em transporte e os prazos só começam no recebimento.",
                "proximo_passo": "Aguardar a entrega. Em caso de avaria no transporte, recusar o recebimento e contatar a loja imediatamente.",
            }

        today = self._clock.today()
        received = order.estimated_delivery or order.order_date
        assumptions = [
            f"O sistema não registra a data real de recebimento. Foi usada a previsão de entrega ({received:%d/%m/%Y}). Se o recebimento foi depois, a equipe pode reavaliar.",
        ]
        if reason == "arrependimento":
            return self._assess_regret(today, received, assumptions)
        if reason == "preferencia":
            return self._assess_preference(today, received, assumptions)
        return self._assess_defect(today, order.order_date, received, assumptions)

    def _assess_regret(self, today: date, received: date, assumptions: list[str]) -> dict:
        deadline = received + timedelta(days=REGRET_DAYS)
        assumptions.append("O sistema não registra o canal da compra. O direito de arrependimento vale para compras online; a equipe confirma o canal.")
        result = {
            "elegivel": today <= deadline,
            "prazo_final": f"{deadline:%d/%m/%Y}",
            "premissas": assumptions,
            "secao_do_manual": "4.1",
        }
        if result["elegivel"]:
            result["condicoes"] = [
                "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
                "Reembolso na mesma forma de pagamento original em até 10 dias úteis.",
                "O frete de devolução é por conta da loja.",
            ]
            result["proximo_passo"] = "Registrar encaminhamento para a equipe dar sequência à devolução."
        else:
            result["explicacao"] = f"O prazo de {REGRET_DAYS} dias corridos após o recebimento terminou."
            result["alternativas"] = "Se houver defeito de fabricação, avaliar pelo motivo 'defeito'."
        return result

    def _assess_preference(self, today: date, received: date, assumptions: list[str]) -> dict:
        deadline = received + timedelta(days=PREFERENCE_DAYS)
        assumptions.append("O manual não define o início dos 7 dias. Foi adotada a data de recebimento.")
        result = {
            "elegivel": today <= deadline,
            "prazo_final": f"{deadline:%d/%m/%Y}",
            "premissas": assumptions,
            "secao_do_manual": "4.3",
        }
        if result["elegivel"]:
            result["condicoes"] = [
                "Produto em perfeito estado e na embalagem original.",
                "Sujeito à disponibilidade do produto desejado.",
                "Diferenças de valor são cobradas ou reembolsadas conforme o caso.",
                "Não vale para instrumentos personalizados, nem compras em liquidação com aviso de venda final, nem boquilhas.",
            ]
            result["proximo_passo"] = "Registrar encaminhamento para a equipe dar sequência à troca."
        else:
            result["explicacao"] = f"O prazo de {PREFERENCE_DAYS} dias para troca por preferência terminou."
        return result

    def _assess_defect(self, today: date, purchased: date, received: date, assumptions: list[str]) -> dict:
        exchange_deadline = purchased + timedelta(days=DEFECT_EXCHANGE_DAYS)
        warranty_deadline = received + timedelta(days=LEGAL_WARRANTY_DAYS)
        in_exchange = today <= exchange_deadline
        in_warranty = today <= warranty_deadline
        result = {
            "elegivel": in_exchange,
            "troca_na_loja_ate": f"{exchange_deadline:%d/%m/%Y}",
            "dentro_da_troca_na_loja": in_exchange,
            "garantia_legal_ate": f"{warranty_deadline:%d/%m/%Y}",
            "dentro_da_garantia_legal": in_warranty,
            "premissas": assumptions,
            "secao_do_manual": "4.2 e 8",
            "exclusoes": "Mau uso, quedas, umidade excessiva, modificações não autorizadas e desgaste natural não são cobertos.",
        }
        if in_exchange:
            result["proximo_passo"] = "Registrar encaminhamento para a equipe dar sequência à troca."
        else:
            result["explicacao"] = f"O prazo de {DEFECT_EXCHANGE_DAYS} dias para troca na loja terminou."
            result["proximo_passo"] = (
                "Acionar a garantia diretamente com o fabricante, conforme o certificado que acompanha o produto. "
                "A loja pode intermediar o processo mediante solicitação."
            )
        return result

    # Handover

    def register_ticket(self, kind: str, summary: str, customer_name: str | None = None, contact: str | None = None) -> dict:
        if kind not in TICKET_KINDS:
            return {"status": "tipo_invalido", "tipos_validos": list(TICKET_KINDS)}
        protocol = self._storage.create_ticket(self._session.id, kind, summary[:1000], customer_name, contact, self._clock.now())
        result = {"status": "ok", "protocolo": protocol}
        if kind == "reclamacao":
            result["prazo_de_retorno"] = "24 horas úteis"
        if not self._clock.is_open():
            result["loja_reabre"] = f"{self._clock.next_opening():%d/%m/%Y às %H:%M}"
        return result


def tool_schemas(policies: PolicyBook, categories: list[str]) -> list[dict]:
    """Provider-neutral tool definitions. Output is deterministic, which keeps the prompt cache valid."""
    verification = {
        "email": {"type": "string", "description": "E-mail informado pelo cliente nesta conversa."},
        "phone": {"type": "string", "description": "Telefone informado pelo cliente nesta conversa."},
    }
    return [
        {
            "name": "search_products",
            "description": "Busca produtos disponíveis para compra por categoria, faixa de preço e texto (marca, material, tipo de corda, uso). Use para perguntas abertas, como opções de um tipo de instrumento ou dentro de um orçamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": sorted(categories), "description": "Categoria do catálogo."},
                    "query": {"type": "string", "description": "Palavras que devem constar no produto. Ex.: nylon, eletroacústico, Yamaha."},
                    "max_price": {"type": "number", "description": "Preço máximo em reais."},
                    "min_price": {"type": "number", "description": "Preço mínimo em reais."},
                },
            },
        },
        {
            "name": "get_product",
            "description": "Consulta um produto específico pelo nome ou modelo, em qualquer situação: preço, promoção ativa ou encerrada, parcelamento, disponibilidade, descrição, especificações e alternativas. Use quando o cliente citar um produto que ainda não veio em uma consulta.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Nome ou modelo do produto. Ex.: Takamine GD20."}},
                "required": ["query"],
            },
        },
        {
            "name": "list_active_promotions",
            "description": "Lista os produtos disponíveis com promoção ativa agora.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_policy",
            "description": (
                "Consulta seções do manual de políticas da loja. Use para regras e informações institucionais: endereço, horários, pagamento, trocas, frete, garantia e privacidade. "
                "Peça somente as seções necessárias. Uma seção principal inclui suas subseções.\n\nSeções disponíveis:\n"
                + policies.table_of_contents()
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_ids": {"type": "array", "items": {"type": "string"}, "description": "Números das seções. Ex.: [\"4.1\", \"8\"]."}
                },
                "required": ["section_ids"],
            },
        },
        {
            "name": "get_my_orders",
            "description": "Consulta pedidos do próprio cliente. Exige o número do pedido e o e-mail ou telefone do cadastro. Sem o número do pedido, exige o e-mail e o telefone. Passe apenas dados que o cliente informou nesta conversa.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "integer", "description": "Número do pedido."}, **verification},
            },
        },
        {
            "name": "check_return_eligibility",
            "description": "Avalia devolução ou troca de um pedido, a partir das datas e do status. Exige o número do pedido e o e-mail ou telefone do cadastro. Pergunte o motivo antes, se ele não estiver claro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Número do pedido."},
                    "reason": {"type": "string", "enum": list(RETURN_REASONS), "description": "Motivo: arrependimento, defeito de fabricação ou preferência (cor, modelo, tamanho)."},
                    **verification,
                },
                "required": ["order_id", "reason"],
            },
        },
        {
            "name": "register_ticket",
            "description": "Registra uma reclamação ou um encaminhamento para a equipe e devolve o protocolo. Use em reclamações, pedidos para falar com uma pessoa e casos que você não consegue resolver.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(TICKET_KINDS)},
                    "summary": {"type": "string", "description": "Resumo do caso para a equipe, sem repetir dados de verificação."},
                    "customer_name": {"type": "string", "description": "Nome, se o cliente informou."},
                    "contact": {"type": "string", "description": "Contato para retorno, se o cliente informou."},
                },
                "required": ["kind", "summary"],
            },
        },
    ]
