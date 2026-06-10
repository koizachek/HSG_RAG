from __future__ import annotations

import json
from typing import Callable

from langchain.tools import tool

from src.rag.programme_facts import ProgrammeFacts, ProgrammeFactsProvider
from src.rag.programmes import normalize_programme_ids
from src.rag.tool_schemas import ProgrammeFactsInput, RetrieveContextInput


class AgentToolRegistry:
    """Build LangChain tools for lead and programme agents."""

    def __init__(
        self,
        retrieve_context: Callable[[str, str, str | None], str],
        programme_facts_provider: ProgrammeFactsProvider | None = None,
    ) -> None:
        self._retrieve_context = retrieve_context
        self._programme_facts_provider = programme_facts_provider
        self.retrieve_context_tool = self._build_retrieve_context_tool()
        self.programme_facts_tool = (
            self._build_programme_facts_tool()
            if programme_facts_provider is not None
            else None
        )

    def lead_tools(self) -> list:
        tools = [self.retrieve_context_tool]
        if self.programme_facts_tool is not None:
            tools.append(self.programme_facts_tool)
        return tools

    def programme_agent_tools(self) -> list:
        return self.lead_tools()

    def _build_retrieve_context_tool(self):
        return tool(
            name_or_callable="retrieve_context",
            runnable=self._retrieve_context,
            args_schema=RetrieveContextInput,
            description=(
                "Retrieve current programme context from the Weaviate vector "
                "database. This is the primary source of truth for programme "
                "facts, comparisons, eligibility, positioning, deadlines, tuition, "
                "and current admissions details."
            ),
            return_direct=False,
            parse_docstring=False,
        )

    def _build_programme_facts_tool(self):
        return tool(
            name_or_callable="programme_facts",
            runnable=self._programme_facts,
            args_schema=ProgrammeFactsInput,
            description=(
                "Look up narrow structured programme facts derived from the "
                "Weaviate corpus. Use only when a structured helper is useful "
                "for facts such as tuition, deadlines, start dates, duration, "
                "format, language, admissions, or documents. If this conflicts "
                "with retrieve_context, retrieve_context wins."
            ),
            return_direct=False,
            parse_docstring=False,
        )

    def _programme_facts(
        self,
        programmes: list[str],
        fields: list[str] | None = None,
        language: str | None = None,
        query: str | None = None,
    ) -> str:
        provider = self._programme_facts_provider
        normalized_programmes = normalize_programme_ids(programmes)
        normalized_language = language if language in {"de", "en"} else "en"
        requested_fields = [field.strip().lower() for field in (fields or []) if field.strip()]
        if not requested_fields:
            requested_fields = ["tuition", "deadlines", "start_dates", "duration", "admissions", "documents"]

        if provider is None:
            payload = {
                "source": "programme_facts",
                "available": False,
                "programmes": {},
                "warnings": ["programme_facts provider is not configured"],
            }
            return json.dumps(payload, ensure_ascii=False)

        facts_by_programme = provider.get_facts_many(normalized_programmes, normalized_language)
        payload = {
            "source": "programme_facts",
            "source_policy": (
                "Derived from Weaviate and useful as a structured helper. "
                "Use retrieve_context as the primary source of truth if facts conflict."
            ),
            "language": normalized_language,
            "query": query,
            "programmes": {
                programme: self._serialize_facts(
                    facts_by_programme.get(programme, ProgrammeFacts(programme=programme)),
                    requested_fields,
                )
                for programme in normalized_programmes
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _serialize_facts(facts: ProgrammeFacts, fields: list[str]) -> dict:
        structured = facts.structured or {}

        aliases = {
            "cost": "tuition",
            "price": "tuition",
            "deadline": "deadlines",
            "start": "start_dates",
            "starts": "start_dates",
            "admission": "admissions",
            "requirements": "admissions",
            "fit": "fit_points",
            "focus": "focus_points",
            "documents": "documents",
        }

        list_sources = {
            "fit_points": facts.fit_points,
            "focus_points": facts.focus_points,
            "timing_points": facts.timing_points,
            "documents": facts.document_points,
        }

        values: dict[str, object] = {}
        missing: list[str] = []

        for requested in fields:
            field = aliases.get(requested, requested)
            value = None
            if field in structured:
                value = structured[field]
            elif field in list_sources:
                value = list_sources[field]
            elif field == "documents":
                value = facts.document_points
            elif field == "admissions":
                value = structured.get("admissions") or facts.fit_points
            elif field in {"duration", "format", "language", "locations", "deadlines", "start_dates", "tuition"}:
                value = structured.get(field)

            has_value = bool(value)
            if has_value:
                values[requested] = value
            else:
                missing.append(requested)

        return {
            "available": facts.source_available,
            "facts": values,
            "missing_fields": missing,
            "warnings": [] if facts.source_available else ["No structured facts available for this programme/language."],
        }
