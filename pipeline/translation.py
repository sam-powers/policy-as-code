"""
CFR Translation Agent.

Translates cached CFR section text into FactGraph node definitions using the LLM.
Caches translations to disk. Validates schema post-translation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from pydantic import ValidationError

from fact_graph.schema import (
    FactGraph,
    FactNode,
    FactStatus,
    ValidationReport,
)
from .cache import DATA_DIR, read_cache, write_cache

load_dotenv()

INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00
COST_LOG_PATH = DATA_DIR / "cost_log.json"

SYSTEM_PROMPT = """\
You are a policy analyst building a structured fact graph for benefit eligibility determination.
Your job is to translate regulatory text into structured FactNode definitions.
A FactNode represents a single discrete fact that must be determined about an applicant.
Facts have dependencies (other facts they depend on) and conditions (logic that resolves them).

Rules:
- Each fact must be atomic — one concept per node.
- Dependencies must be explicit — never implicit.
- If a rule is ambiguous or underspecified, flag it with ambiguity_notes rather than guessing.
- Every condition must trace back to a specific CFR citation with paragraph.
- Use snake_case IDs that are self-documenting.

ConditionOperator values: AND, OR, NOT, EQUALS, GREATER_THAN, LESS_THAN, IN, MULTIPLY, SUBTRACT, ADD.
- For MULTIPLY/SUBTRACT/ADD: operands are [fact_id_or_numeric_literal, ...], result_value must be null.
- For EQUALS: operands are [fact_id, comparison_value_as_string].
- For AND/OR: operands are nested Condition objects or fact_id strings.
- For NOT: single operand (fact_id string or nested Condition).

Return ONLY valid JSON: a list of FactNode objects matching the schema below.
No preamble, no explanation outside the JSON array.
"""

FACTNODE_SCHEMA_SUMMARY = """\
FactNode schema (Pydantic v2):
{
  "id": str (snake_case),
  "label": str (human-readable),
  "fact_type": "boolean" | "categorical" | "numeric" | "date",
  "dependencies": [str, ...],  // IDs of FactNodes this depends on
  "conditions": [
    {
      "operator": "AND"|"OR"|"NOT"|"EQUALS"|"GREATER_THAN"|"LESS_THAN"|"IN"|"MULTIPLY"|"SUBTRACT"|"ADD",
      "operands": [str_or_nested_condition, ...],
      "result_value": bool | number | str | null
    }
  ],
  "cfr_citations": [
    {
      "title": int,
      "part": int,
      "section": str,
      "paragraph": str | null,
      "text_excerpt": str  // verbatim excerpt from CFR
    }
  ],
  "ambiguity_notes": str | null,
  "status": "unknown",
  "value": null
}
"""

REQUIRED_TERMINAL_FACTS = [
    "applicant_eligible_for_rental_assistance",
    "maximum_award_amount",
]


class TranslationAgent:
    """
    Translates CFR section text (from disk cache) into FactGraph node definitions.

    Args:
        anthropic_client: Injected anthropic.Anthropic for testing (None = real client).
    """

    def __init__(self, anthropic_client: anthropic.Anthropic | None = None) -> None:
        self._llm = anthropic_client

    def _get_llm(self) -> anthropic.Anthropic:
        if self._llm is not None:
            return self._llm
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "API key not configured. Set ANTHROPIC_API_KEY in .env to run the pipeline."
            )
        self._llm = anthropic.Anthropic(api_key=api_key)
        return self._llm

    def translate_section(
        self,
        title: int,
        section: str,
        section_text: str,
        existing_fact_ids: list[str],
        force: bool = False,
    ) -> list[FactNode]:
        """
        Translate one CFR section into a list of FactNodes.

        Returns cached result if available (unless force=True).
        """
        cache_key = f"title_{title}_section_{section.replace('.', '_')}"
        cached = read_cache("fact_graph_defs", cache_key, force=force)
        if cached is not None:
            raw_nodes: list[Any] = cached.get("nodes", [])
            return [FactNode.model_validate(n) for n in raw_nodes]

        llm = self._get_llm()

        existing_ids_str = (
            "Previously defined fact IDs (do not redefine):\n"
            + "\n".join(f"  - {fid}" for fid in existing_fact_ids)
            if existing_fact_ids
            else "No facts defined yet."
        )

        user_prompt = f"""\
{FACTNODE_SCHEMA_SUMMARY}

{existing_ids_str}

CFR SECTION TEXT (Title {title}, §{section}):
{section_text[:10000]}

Return a JSON array of FactNode objects derived from this section.
"""

        response = llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._log_cost(f"title_{title}_section_{section}", response.usage)

        first_block = response.content[0] if response.content else None
        text = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else "[]"
        # Strip markdown code fences if present.
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()

        raw: list[Any] = json.loads(text)
        nodes: list[FactNode] = []
        errors: list[str] = []
        for i, raw_node in enumerate(raw):
            try:
                nodes.append(FactNode.model_validate(raw_node))
            except ValidationError as e:
                errors.append(f"Node {i}: {e}")

        if errors:
            raise ValueError(
                f"Translation produced invalid FactNodes for §{section}:\n" + "\n".join(errors)
            )

        # Cache the validated output.
        write_cache(
            "fact_graph_defs",
            cache_key,
            {"section": section, "nodes": [n.model_dump() for n in nodes]},
        )
        return nodes

    def build_graph_from_cache(self) -> FactGraph:
        """
        Assemble a complete FactGraph from all cached translation outputs.
        """
        defs_dir = DATA_DIR / "fact_graph_defs"
        all_nodes: dict[str, FactNode] = {}

        for json_file in sorted(defs_dir.glob("title_*.json")):
            data = json.loads(json_file.read_text())
            for raw_node in data.get("nodes", []):
                node = FactNode.model_validate(raw_node)
                all_nodes[node.id] = node

        return FactGraph(
            nodes=all_nodes,
            terminal_fact_ids=REQUIRED_TERMINAL_FACTS,
        )

    def validate_graph(self, graph: FactGraph) -> ValidationReport:
        """
        Validate a FactGraph for consistency.

        Checks:
        - All dependency IDs reference existing nodes.
        - Terminal facts are present.
        - Ambiguous facts are surfaced.
        """
        all_ids = set(graph.nodes.keys())
        broken_deps: list[str] = []
        ambiguous: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        for node in graph.nodes.values():
            for dep_id in node.dependencies:
                if dep_id not in all_ids:
                    broken_deps.append(f"{node.id} → {dep_id}")
            if node.status == FactStatus.AMBIGUOUS or node.ambiguity_notes:
                ambiguous.append(node.id)

        missing_terminals = [fid for fid in REQUIRED_TERMINAL_FACTS if fid not in all_ids]
        if missing_terminals:
            errors.append(f"Missing terminal facts: {missing_terminals}")

        if broken_deps:
            errors.append(f"Broken dependency references: {broken_deps}")

        report = ValidationReport(
            valid=len(errors) == 0,
            terminal_facts_present=len(missing_terminals) == 0,
            missing_terminal_facts=missing_terminals,
            broken_dependency_refs=broken_deps,
            ambiguous_facts=ambiguous,
            errors=errors,
            warnings=warnings,
        )

        write_cache(
            "fact_graph_defs",
            "validation_report",
            report.model_dump(),
        )
        return report

    def run_pipeline(
        self,
        manifest: dict[str, Any],
        force: bool = False,
    ) -> ValidationReport:
        """
        Translate all relevant sections from the manifest and validate.
        """
        relevant_sections = [
            entry
            for entry in manifest.get("fetched_sections", [])
            if entry.get("relevant", False)
        ]

        existing_ids: list[str] = []
        for entry in relevant_sections:
            title = entry["title"]
            section = entry["section"]
            cache_key = f"title_{title}_section_{section.replace('.', '_')}"
            section_data = read_cache("cfr_cache", cache_key)
            if not section_data:
                continue
            section_text = section_data.get("content", "")
            try:
                nodes = self.translate_section(
                    title, section, section_text, existing_ids, force=force
                )
                existing_ids.extend(n.id for n in nodes)
            except (ValueError, RuntimeError) as e:
                print(f"[translation] Error translating §{section}: {e}")

        graph = self.build_graph_from_cache()
        return self.validate_graph(graph)

    def _log_cost(self, label: str, usage: Any) -> None:
        import json as _json

        entry = {
            "timestamp": os.getenv("ECFR_DATE", ""),
            "section": label,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": (
                usage.input_tokens / 1_000_000 * INPUT_COST_PER_M
                + usage.output_tokens / 1_000_000 * OUTPUT_COST_PER_M
            ),
        }
        existing: list[Any] = []
        if COST_LOG_PATH.exists():
            try:
                existing = _json.loads(COST_LOG_PATH.read_text())
            except Exception:
                pass
        existing.append(entry)
        COST_LOG_PATH.write_text(_json.dumps(existing, indent=2))
