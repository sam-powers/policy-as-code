"""Provenance assembly: builds ResolutionTrace and Determination from engine state."""

from __future__ import annotations

from datetime import datetime

from .schema import (
    ConditionFired,
    Determination,
    FactGraph,
    FactNode,
    FactStatus,
    FactValue,
    ResolutionTrace,
)


def build_trace(
    node: FactNode,
    conditions_fired: list[ConditionFired],
    dependency_snapshots: dict[str, FactNode],
) -> ResolutionTrace:
    """Build a ResolutionTrace for a single fact from engine state."""
    dep_values: dict[str, FactValue] = {
        dep_id: dependency_snapshots[dep_id].value
        for dep_id in node.dependencies
        if dep_id in dependency_snapshots
    }
    return ResolutionTrace(
        fact_id=node.id,
        label=node.label,
        fact_type=node.fact_type,
        value=node.value,
        status=node.status,
        conditions_fired=conditions_fired,
        cfr_citations=node.cfr_citations,
        dependency_ids=list(node.dependencies),
        dependency_values=dep_values,
    )


def build_determination(
    graph: FactGraph,
    node_map: dict[str, FactNode],
    conditions_fired_map: dict[str, list[ConditionFired]],
    input_facts: dict[str, FactValue],
    scenario_label: str | None = None,
) -> Determination:
    """Assemble a Determination from the engine's resolved node map."""
    terminal_traces: dict[str, ResolutionTrace] = {}
    resolved_traces: dict[str, ResolutionTrace] = {}
    unresolved: list[str] = []
    ambiguous: list[str] = []
    unresolved_inputs: list[str] = []

    for fact_id, node in node_map.items():
        dep_snapshots = {d: node_map[d] for d in node.dependencies if d in node_map}
        fired = conditions_fired_map.get(fact_id, [])

        if node.status == FactStatus.UNKNOWN and len(node.dependencies) == 0:
            unresolved_inputs.append(fact_id)
        elif node.status == FactStatus.UNRESOLVED:
            unresolved.append(fact_id)
        elif node.status == FactStatus.AMBIGUOUS:
            ambiguous.append(fact_id)
        elif node.status == FactStatus.RESOLVED:
            trace = build_trace(node, fired, dep_snapshots)
            if fact_id in graph.terminal_fact_ids:
                terminal_traces[fact_id] = trace
            else:
                resolved_traces[fact_id] = trace

    return Determination(
        program=graph.program,
        scenario_label=scenario_label,
        input_facts=input_facts,
        terminal_facts=terminal_traces,
        resolved_facts=resolved_traces,
        unresolved_facts=unresolved,
        ambiguous_facts=ambiguous,
        unresolved_inputs=unresolved_inputs,
        timestamp=datetime.utcnow(),
    )


def format_determination_text(det: Determination) -> str:
    """Render a Determination as human-readable CLI output."""
    lines: list[str] = []

    # --- Terminal determination ---
    eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    max_award_trace = det.terminal_facts.get("maximum_award_amount")

    if eligible_trace and eligible_trace.status == FactStatus.RESOLVED:
        verdict = "ELIGIBLE" if eligible_trace.value else "INELIGIBLE"
        lines.append(f"\nDETERMINATION: {verdict}")
    else:
        lines.append("\nDETERMINATION: INCOMPLETE (awaiting inputs)")

    lines.append(f"Program: {det.program}")

    if max_award_trace and max_award_trace.status == FactStatus.RESOLVED:
        lines.append(f"Max Award: ${max_award_trace.value:,.2f}")

    # --- Resolved facts ---
    if det.resolved_facts or det.terminal_facts:
        lines.append("\nRESOLVED FACTS:")
        all_resolved = {**det.resolved_facts, **det.terminal_facts}
        for fact_id, trace in sorted(all_resolved.items()):
            citations = ""
            if trace.cfr_citations:
                c = trace.cfr_citations[0]
                para = c.paragraph or ""
                citations = f" — {c.title} CFR §{c.section}{para}"
            lines.append(f"  ✓ {fact_id} ({trace.value}){citations}")

    # --- Unresolved inputs ---
    if det.unresolved_inputs:
        lines.append("\nUNRESOLVED FACTS (incomplete determination):")
        for fact_id in sorted(det.unresolved_inputs):
            lines.append(f"  ? {fact_id} — awaiting input")

    if det.unresolved_facts:
        for fact_id in sorted(det.unresolved_facts):
            lines.append(f"  ? {fact_id} — blocked by missing upstream facts")

    # --- Ambiguity flags ---
    if det.ambiguous_facts:
        lines.append("\nAMBIGUITY FLAGS:")
        for fact_id in sorted(det.ambiguous_facts):
            lines.append(f"  ⚠ {fact_id} — see ambiguity_notes")

    return "\n".join(lines)


def format_trace_text(trace: ResolutionTrace) -> str:
    """Render a ResolutionTrace as human-readable text."""
    lines = [
        f"Trace: {trace.fact_id}",
        f"  Label:  {trace.label}",
        f"  Type:   {trace.fact_type.value}",
        f"  Status: {trace.status.value}",
        f"  Value:  {trace.value}",
    ]
    if trace.dependency_ids:
        lines.append("  Dependencies:")
        for dep_id in trace.dependency_ids:
            dep_val = trace.dependency_values.get(dep_id, "<unknown>")
            lines.append(f"    {dep_id} = {dep_val}")
    if trace.conditions_fired:
        lines.append("  Conditions fired:")
        for cf in trace.conditions_fired:
            lines.append(f"    [{cf.condition_index}] {cf.operator.value} → {cf.result_value}")
    if trace.cfr_citations:
        lines.append("  CFR citations:")
        for c in trace.cfr_citations:
            para = c.paragraph or ""
            lines.append(f"    {c.title} CFR §{c.section}{para}: \"{c.text_excerpt[:80]}\"")
    return "\n".join(lines)
