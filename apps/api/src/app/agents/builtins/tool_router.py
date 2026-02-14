"""
Tool Router — мета-tool для автоматической маршрутизации запросов к нужным tools.

Принимает запрос пользователя и список доступных tools,
анализирует intent и вызывает подходящие tools автоматически.

Это позволяет агенту-ассистенту не знать заранее какие tools вызывать —
Tool Router сам определяет это на основе запроса и доступных инструментов.
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar, Optional
import json

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "The user's original query or request to route to appropriate tools. "
                "The router will analyze this and determine which tools to call."
            )
        },
        "tool_hints": {
            "type": "array",
            "description": "Optional hints about which tool groups to prefer (e.g. ['rag', 'collection'])",
            "items": {"type": "string"},
        },
        "max_tools": {
            "type": "integer",
            "description": "Maximum number of tools to call (default: 3)",
            "default": 3,
            "minimum": 1,
            "maximum": 5,
        },
    },
    "required": ["query"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "description": "Results from each tool call",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "success": {"type": "boolean"},
                    "data": {},
                    "error": {"type": "string"},
                },
            },
        },
        "tools_called": {"type": "integer"},
        "summary": {"type": "string"},
    },
}


@register_tool
class ToolRouterTool(VersionedTool):
    """
    Мета-tool для автоматической маршрутизации запросов.

    Анализирует запрос пользователя, определяет какие из доступных tools
    подходят для ответа, вызывает их и агрегирует результаты.

    Используется агентом-ассистентом как единственный tool —
    вся логика выбора конкретных tools инкапсулирована здесь.
    """

    tool_slug: ClassVar[str] = "system.router"
    tool_group: ClassVar[str] = "system"
    name: ClassVar[str] = "Tool Router"
    description: ClassVar[str] = (
        "Automatically routes a user query to the most appropriate tools. "
        "Analyzes the query, selects relevant tools from the available set, "
        "calls them, and returns aggregated results."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version: intent-based routing to RAG and collection tools",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Route query to appropriate tools based on intent analysis.
        """
        from app.agents.handlers.versioned_tool import tool_registry

        query = args["query"]
        tool_hints = args.get("tool_hints", [])
        max_tools = min(args.get("max_tools", 3), 5)

        logger.info(
            f"Tool Router: query='{query[:80]}', hints={tool_hints}, "
            f"max_tools={max_tools}, tenant={ctx.tenant_id}"
        )

        # 1. Discover available tools (exclude self to avoid recursion)
        all_tools = tool_registry.get_all()
        available = [t for t in all_tools if t.tool_slug != self.tool_slug]

        if not available:
            return ToolResult.fail("No tools available for routing")

        # 2. Determine which tools to call based on query analysis
        plan = self._plan_tool_calls(query, available, tool_hints, max_tools)

        if not plan:
            return ToolResult.ok(
                data={
                    "results": [],
                    "tools_called": 0,
                    "summary": "No suitable tools found for this query.",
                }
            )

        # 3. Execute planned tool calls
        results: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []

        for tool_slug, tool_args in plan:
            tool = tool_registry.get(tool_slug)
            if not tool:
                results.append({
                    "tool": tool_slug,
                    "success": False,
                    "error": f"Tool '{tool_slug}' not found",
                })
                continue

            try:
                logger.info(f"Tool Router calling: {tool_slug}")
                result = await tool.execute(ctx, tool_args)

                entry: Dict[str, Any] = {
                    "tool": tool_slug,
                    "success": result.success,
                }
                if result.success:
                    entry["data"] = result.data
                    if result.metadata.get("sources"):
                        sources.extend(result.metadata["sources"])
                else:
                    entry["error"] = result.error

                results.append(entry)

            except Exception as e:
                logger.error(f"Tool Router: {tool_slug} failed: {e}")
                results.append({
                    "tool": tool_slug,
                    "success": False,
                    "error": str(e),
                })

        successful = [r for r in results if r.get("success")]
        summary = self._build_summary(query, results)

        logger.info(
            f"Tool Router complete: {len(results)} calls, "
            f"{len(successful)} successful"
        )

        return ToolResult.ok(
            data={
                "results": results,
                "tools_called": len(results),
                "summary": summary,
            },
            sources=sources,
        )

    def _plan_tool_calls(
        self,
        query: str,
        available: List[VersionedTool],
        hints: List[str],
        max_tools: int,
    ) -> List[tuple[str, Dict[str, Any]]]:
        """
        Determine which tools to call and with what arguments.

        Uses keyword-based intent detection (no LLM call — fast and deterministic).
        """
        query_lower = query.lower()
        plan: List[tuple[str, Dict[str, Any]]] = []

        # Build tool index by group
        by_group: Dict[str, List[VersionedTool]] = {}
        for t in available:
            by_group.setdefault(t.tool_group, []).append(t)

        # If hints provided, prioritize those groups
        if hints:
            for hint in hints:
                if hint in by_group:
                    for t in by_group[hint]:
                        call = self._match_tool(t, query, query_lower)
                        if call:
                            plan.append(call)
                            if len(plan) >= max_tools:
                                return plan

        # Intent-based matching for remaining slots
        if len(plan) < max_tools:
            # RAG search: knowledge base, documentation, docs, policy, guide
            rag_keywords = [
                "документ", "знани", "база знаний", "knowledge",
                "document", "policy", "guide", "руководств",
                "инструкц", "регламент", "найди в базе",
                "поиск по базе", "search knowledge",
            ]
            if any(kw in query_lower for kw in rag_keywords):
                rag_tool = self._find_tool(available, "rag.search")
                if rag_tool and not self._already_planned(plan, "rag.search"):
                    plan.append(("rag.search", {"query": query, "k": 5}))

            # Collection search: data, records, table, collection
            coll_keywords = [
                "коллекц", "collection", "данные", "data",
                "запис", "record", "таблиц", "table",
                "найди запис", "покажи данные", "список",
                "сколько", "статистик", "count", "aggregate",
            ]
            if any(kw in query_lower for kw in coll_keywords):
                # Try to extract collection slug from query
                coll_slug = self._extract_collection_slug(query, available)

                if coll_slug:
                    # Determine if aggregate or search
                    agg_keywords = [
                        "сколько", "count", "сумм", "sum",
                        "средн", "avg", "average", "статистик",
                        "aggregate", "итого", "total",
                    ]
                    if any(kw in query_lower for kw in agg_keywords):
                        agg_tool = self._find_tool(available, "collection.aggregate")
                        if agg_tool and not self._already_planned(plan, "collection.aggregate"):
                            plan.append((
                                "collection.aggregate",
                                {
                                    "collection_slug": coll_slug,
                                    "metrics": [{"function": "count"}],
                                },
                            ))
                    else:
                        search_tool = self._find_tool(available, "collection.search")
                        if search_tool and not self._already_planned(plan, "collection.search"):
                            plan.append((
                                "collection.search",
                                {
                                    "collection_slug": coll_slug,
                                    "query": query,
                                    "limit": 20,
                                },
                            ))

            # DCBox / NetBox: network infrastructure, DCIM, IPAM
            dcbox_keywords = [
                "device", "девайс", "устройств", "сервер", "server",
                "switch", "свитч", "коммутатор", "router", "роутер",
                "маршрутизатор", "firewall", "фаервол",
                "site", "сайт", "площадк", "дата-центр", "datacenter", "dc",
                "rack", "стойк", "шкаф",
                "prefix", "префикс", "подсет", "subnet", "сеть", "network",
                "ip", "адрес", "address", "ipam", "dcim",
                "netbox", "dcbox", "инфраструктур", "infrastructure",
                "vlan", "vrf", "интерфейс", "interface",
            ]
            if any(kw in query_lower for kw in dcbox_keywords):
                dcbox_tool = self._select_dcbox_tool(query_lower, available)
                if dcbox_tool and not self._already_planned(plan, dcbox_tool[0]):
                    plan.append(dcbox_tool)

        # Fallback: if nothing matched, try RAG as default
        if not plan:
            rag_tool = self._find_tool(available, "rag.search")
            if rag_tool:
                plan.append(("rag.search", {"query": query, "k": 5}))

        return plan[:max_tools]

    def _match_tool(
        self, tool: VersionedTool, query: str, query_lower: str
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """Try to match a specific tool to the query."""
        if tool.tool_slug == "rag.search":
            return ("rag.search", {"query": query, "k": 5})
        if tool.tool_slug == "collection.search":
            return ("collection.search", {"query": query, "limit": 20})
        if tool.tool_slug == "collection.get":
            return None  # Needs explicit ID
        if tool.tool_slug == "collection.aggregate":
            return (
                "collection.aggregate",
                {"metrics": [{"function": "count"}]},
            )
        # DCBox tools
        if tool.tool_slug.startswith("dcbox."):
            return (tool.tool_slug, {"q": query, "limit": 20})
        return None

    def _select_dcbox_tool(
        self,
        query_lower: str,
        available: List[VersionedTool],
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        Select the most appropriate DCBox tool based on query keywords.
        Falls back to dcbox.devices if no specific match.
        """
        # IP addresses
        addr_kw = ["ip", "адрес", "address", "ip-адрес"]
        if any(kw in query_lower for kw in addr_kw):
            tool = self._find_tool(available, "dcbox.addresses")
            if tool:
                return ("dcbox.addresses", {"limit": 20})

        # Prefixes / subnets
        prefix_kw = ["prefix", "префикс", "подсет", "subnet", "vlan", "vrf"]
        if any(kw in query_lower for kw in prefix_kw):
            tool = self._find_tool(available, "dcbox.prefixes")
            if tool:
                return ("dcbox.prefixes", {"limit": 20})

        # Sites
        site_kw = ["site", "сайт", "площадк", "дата-центр", "datacenter"]
        if any(kw in query_lower for kw in site_kw):
            tool = self._find_tool(available, "dcbox.sites")
            if tool:
                return ("dcbox.sites", {"limit": 20})

        # Racks
        rack_kw = ["rack", "стойк", "шкаф"]
        if any(kw in query_lower for kw in rack_kw):
            tool = self._find_tool(available, "dcbox.racks")
            if tool:
                return ("dcbox.racks", {"limit": 20})

        # Default: devices (most common DCIM query)
        device_kw = [
            "device", "девайс", "устройств", "сервер", "server",
            "switch", "свитч", "коммутатор", "router", "роутер",
            "маршрутизатор", "firewall", "фаервол",
            "dcim", "netbox", "dcbox", "инфраструктур", "infrastructure",
        ]
        if any(kw in query_lower for kw in device_kw):
            tool = self._find_tool(available, "dcbox.devices")
            if tool:
                return ("dcbox.devices", {"limit": 20})

        return None

    def _find_tool(
        self, available: List[VersionedTool], slug: str
    ) -> Optional[VersionedTool]:
        """Find tool by slug."""
        return next((t for t in available if t.tool_slug == slug), None)

    def _already_planned(
        self, plan: List[tuple[str, Dict[str, Any]]], slug: str
    ) -> bool:
        """Check if tool is already in the plan."""
        return any(s == slug for s, _ in plan)

    def _extract_collection_slug(
        self, query: str, available: List[VersionedTool]
    ) -> Optional[str]:
        """
        Try to extract collection slug from query text.
        Returns None if no collection can be identified.
        """
        # This is a simple heuristic — in production, LLM would do this better.
        # For now, return None to let the collection tools handle it.
        return None

    def _build_summary(
        self, query: str, results: List[Dict[str, Any]]
    ) -> str:
        """Build a human-readable summary of routing results."""
        if not results:
            return "No tools were called."

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        parts = []
        parts.append(f"Called {len(results)} tool(s) for query.")

        if successful:
            tool_names = ", ".join(r["tool"] for r in successful)
            parts.append(f"Successful: {tool_names}.")

        if failed:
            tool_names = ", ".join(r["tool"] for r in failed)
            parts.append(f"Failed: {tool_names}.")

        return " ".join(parts)
