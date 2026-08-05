"""Danh muc tool + kiem soat quyen truy cap du lieu.

Phan quyen o day la RANG BUOC THUC THI, khong phai mo ta tren tai lieu.
Moi tool khai bao no doc nhung bang nao. Moi agent khai bao no duoc doc nhung
bang nao (src/config.AGENTS[...].allowed_tables). Neu agent goi tool doi hoi bang
ngoai whitelist -> ToolAccessError, chay se do ngay chu khong am tham sai.

Nho vay Policy Agent (allowed_tables rong) khong the tu tra CSV; no bat buoc phai
ket luan tu handoff card cua agent khac -- dung tinh than A2A cua de bai.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src import config
from src.contracts import Fact
from src.loader import OrderBundle
from src.tools import customer_tools, delivery_tools, order_tools, payment_tools


class ToolAccessError(PermissionError):
    """Agent goi tool nam ngoai quyen truy cap du lieu cua no."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[[OrderBundle], list[Fact]]
    required_tables: frozenset[str]
    owner_agent: str


def _spec(name, description, fn, tables, owner) -> ToolSpec:
    return ToolSpec(name, description, fn, frozenset(tables), owner)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    # -- customer_agent ----------------------------------------------------
    "get_customer_identity": _spec(
        "get_customer_identity",
        "Tra customer_unique_id dung sau order (orders.customer_id chi la ID cua mot don).",
        customer_tools.get_customer_identity,
        {"customers", "orders"},
        "customer_agent",
    ),
    "get_customer_order_history": _spec(
        "get_customer_order_history",
        "Liet ke order khac cua cung customer_unique_id, phuc vu secondary issue repeat_customer.",
        customer_tools.get_customer_order_history,
        {"customers", "orders"},
        "customer_agent",
    ),
    # -- order_product_agent -----------------------------------------------
    "get_order_header": _spec(
        "get_order_header",
        "Tra order_status, quyet dinh hai luat uu tien cao nhat (canceled / unavailable).",
        order_tools.get_order_header,
        {"orders"},
        "order_product_agent",
    ),
    "get_order_items": _spec(
        "get_order_items",
        "Liet ke item va seller cua order, phuc vu multi_item_order va multi_seller_order.",
        order_tools.get_order_items,
        {"orders", "order_items", "sellers"},
        "order_product_agent",
    ),
    "get_product_context": _spec(
        "get_product_context",
        "Tra product_id va category (da dedup), phuc vu multiple_categories.",
        order_tools.get_product_context,
        {"order_items", "products", "category_translation"},
        "order_product_agent",
    ),
    # -- payment_agent ------------------------------------------------------
    "get_payment_rows": _spec(
        "get_payment_rows",
        "Liet ke payment row, payment_type va tong payment_value.",
        payment_tools.get_payment_rows,
        {"order_payments"},
        "payment_agent",
    ),
    "reconcile_payments": _spec(
        "reconcile_payments",
        "Doi soat tong payment voi sum(price)+sum(freight), tinh difference_brl va reconciled.",
        payment_tools.reconcile_payments,
        {"order_payments", "order_items"},
        "payment_agent",
    ),
    # -- delivery_agent -----------------------------------------------------
    "get_delivery_timestamps": _spec(
        "get_delivery_timestamps",
        "Tra ba moc thoi gian giao hang va tinh delivery_variance_hours.",
        delivery_tools.get_delivery_timestamps,
        {"orders"},
        "delivery_agent",
    ),
    "analyze_seller_handoff": _spec(
        "analyze_seller_handoff",
        "Tinh handoff_variance_hours cho tung seller va liet ke seller ban giao muon.",
        delivery_tools.analyze_seller_handoff,
        {"orders", "order_items"},
        "delivery_agent",
    ),
}


def tools_for_agent(agent_name: str) -> list[ToolSpec]:
    """Cac tool mot agent duoc phep goi, da loc theo whitelist bang du lieu."""
    agent = config.AGENTS.get(agent_name)
    if agent is None:
        raise KeyError(f"Khong co agent ten '{agent_name}'")
    allowed = set(agent.allowed_tables)
    return [
        spec
        for spec in TOOL_REGISTRY.values()
        if spec.owner_agent == agent_name and spec.required_tables <= allowed
    ]


def assert_can_use(agent_name: str, tool_name: str) -> ToolSpec:
    """Chan truy cap trai phep truoc khi tool chay."""
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None:
        raise ToolAccessError(f"Tool khong ton tai: {tool_name}")

    agent = config.AGENTS.get(agent_name)
    if agent is None:
        raise ToolAccessError(f"Agent khong ton tai: {agent_name}")

    if spec.owner_agent != agent_name:
        raise ToolAccessError(
            f"Agent '{agent_name}' khong so huu tool '{tool_name}' "
            f"(chu so huu: '{spec.owner_agent}')"
        )

    missing = spec.required_tables - set(agent.allowed_tables)
    if missing:
        raise ToolAccessError(
            f"Agent '{agent_name}' khong co quyen doc bang {sorted(missing)} "
            f"ma tool '{tool_name}' can"
        )
    return spec


def call_tool(agent_name: str, tool_name: str, bundle: OrderBundle) -> list[Fact]:
    """Goi tool sau khi da qua kiem tra quyen."""
    spec = assert_can_use(agent_name, tool_name)
    return spec.fn(bundle)


def describe_tools_for_prompt(agent_name: str) -> str:
    """Mo ta tool dua vao prompt de LLM tu chon tool."""
    lines = []
    for spec in tools_for_agent(agent_name):
        lines.append(f"- {spec.name}: {spec.description}")
    return "\n".join(lines)


__all__ = [
    "TOOL_REGISTRY",
    "ToolAccessError",
    "ToolSpec",
    "assert_can_use",
    "call_tool",
    "describe_tools_for_prompt",
    "tools_for_agent",
]
