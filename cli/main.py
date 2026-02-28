"""
Disaster Assistance Fact Graph — CLI

Commands:
  run-pipeline  -- Fetch CFR sections and translate to Fact Graph (requires API key)
  determine     -- Run an applicant scenario and print determination
  test          -- Run the synthetic test suite
  show-graph    -- Print fact dependency tree
  show-validation -- Show validation report
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    name="fact-graph",
    help="FEMA IA eligibility Fact Graph CLI",
    add_completion=False,
)

_NO_KEY_MSG = (
    "API key not configured. Set ANTHROPIC_API_KEY in .env to run the pipeline."
)


def _require_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        typer.echo(_NO_KEY_MSG, err=True)
        raise typer.Exit(code=1)
    return key


def _load_graph_from_cache() -> "FactGraph":
    from pipeline.translation import TranslationAgent

    agent = TranslationAgent()
    return agent.build_graph_from_cache()


@app.command("run-pipeline")
def run_pipeline(
    refresh: bool = typer.Option(False, "--refresh", help="Re-fetch and re-translate even if cached."),
) -> None:
    """Fetch CFR sections (discovery) then translate to Fact Graph nodes."""
    _require_api_key()

    from pipeline.discovery import DiscoveryAgent
    from pipeline.translation import TranslationAgent

    typer.echo("[1/3] Running CFR discovery...")
    discovery = DiscoveryAgent()
    manifest = discovery.run(force=refresh)

    relevant = [e for e in manifest.get("fetched_sections", []) if e.get("relevant")]
    typer.echo(
        f"      Fetched {len(manifest.get('fetched_sections', []))} sections; "
        f"{len(relevant)} relevant."
    )

    typer.echo("[2/3] Translating relevant sections to Fact Graph nodes...")
    translator = TranslationAgent()
    report = translator.run_pipeline(manifest, force=refresh)

    typer.echo("[3/3] Validation report:")
    _print_validation(report)

    total_cost = _compute_total_cost()
    if total_cost is not None:
        typer.echo(f"\nEstimated total API cost this run: ${total_cost:.4f}")


@app.command("determine")
def determine(
    input: Path = typer.Option(..., "--input", help="Path to applicant scenario JSON file."),
    scenario_label: Optional[str] = typer.Option(None, "--label", help="Optional label for output."),
) -> None:
    """Run an applicant scenario through the Fact Graph and print determination."""
    from fact_graph.engine import FactGraphEngine
    from fact_graph.provenance import format_determination_text

    if not input.exists():
        typer.echo(f"Error: file not found: {input}", err=True)
        raise typer.Exit(code=1)

    scenario: dict = json.loads(input.read_text())  # type: ignore[type-arg]
    input_facts: dict = scenario.get("inputs", scenario)  # type: ignore[type-arg]

    graph = _load_graph_from_cache()
    if not graph.nodes:
        typer.echo(
            "No Fact Graph found. Run `fact-graph run-pipeline` first "
            "(requires ANTHROPIC_API_KEY).",
            err=True,
        )
        raise typer.Exit(code=1)

    engine = FactGraphEngine(graph)
    engine.load_facts(input_facts)
    engine.resolve()
    det = engine.get_determination(scenario_label=scenario_label or scenario.get("id"))
    typer.echo(format_determination_text(det))


@app.command("test")
def run_tests() -> None:
    """Run the synthetic test suite from data/test_cases/synthetic_cases.json."""
    import importlib.util
    from pathlib import Path as P

    cases_path = P("data/test_cases/synthetic_cases.json")
    if not cases_path.exists():
        typer.echo(
            "No synthetic test cases found. Run `fact-graph run-pipeline` first "
            "(requires ANTHROPIC_API_KEY) or generate test cases manually.",
            err=True,
        )
        raise typer.Exit(code=1)

    from fact_graph.engine import FactGraphEngine
    from fact_graph.schema import FactStatus, TestCase

    cases_raw: list[dict] = json.loads(cases_path.read_text())  # type: ignore[type-arg]
    cases = [TestCase.model_validate(c) for c in cases_raw]

    graph = _load_graph_from_cache()
    passed = 0
    failed = 0

    for case in cases:
        engine = FactGraphEngine(graph)
        engine.load_facts(case.inputs)
        engine.resolve()
        det = engine.get_determination(scenario_label=case.id)

        eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
        if eligible_trace and eligible_trace.status == FactStatus.RESOLVED:
            actual = "eligible" if eligible_trace.value else "ineligible"
        elif det.unresolved_inputs or det.unresolved_facts:
            actual = "incomplete"
        else:
            actual = "unknown"

        if actual == case.expected_determination:
            typer.echo(f"  PASS  {case.id}")
            passed += 1
        else:
            typer.echo(f"  FAIL  {case.id}: expected={case.expected_determination}, got={actual}")
            typer.echo(f"        {case.rationale}")
            failed += 1

    typer.echo(f"\n{passed}/{passed + failed} tests passed.")
    if failed:
        raise typer.Exit(code=1)


@app.command("show-graph")
def show_graph() -> None:
    """Print the Fact Graph as a dependency tree."""
    graph = _load_graph_from_cache()
    if not graph.nodes:
        typer.echo("No Fact Graph found. Run `fact-graph run-pipeline` first.", err=True)
        raise typer.Exit(code=1)

    # Find terminal facts and walk backwards.
    printed: set[str] = set()

    def print_node(fact_id: str, indent: int = 0) -> None:
        if fact_id not in graph.nodes:
            typer.echo("  " * indent + f"? {fact_id} (unknown)")
            return
        node = graph.nodes[fact_id]
        marker = "◉" if fact_id in graph.terminal_fact_ids else "○"
        typer.echo("  " * indent + f"{marker} {fact_id} [{node.fact_type.value}]")
        if fact_id in printed:
            return
        printed.add(fact_id)
        for dep_id in node.dependencies:
            print_node(dep_id, indent + 1)

    typer.echo(f"Fact Graph: {graph.program}\n")
    for terminal_id in graph.terminal_fact_ids:
        print_node(terminal_id)


@app.command("show-validation")
def show_validation() -> None:
    """Display the validation report from the last pipeline run."""
    from pipeline.cache import read_cache

    report_data = read_cache("fact_graph_defs", "validation_report")
    if not report_data:
        typer.echo("No validation report found. Run `fact-graph run-pipeline` first.", err=True)
        raise typer.Exit(code=1)

    from fact_graph.schema import ValidationReport

    report = ValidationReport.model_validate(report_data)
    status = "VALID" if report.valid else "INVALID"
    typer.echo(f"\nValidation Report: {status}")
    typer.echo(f"  Terminal facts present: {report.terminal_facts_present}")

    if report.missing_terminal_facts:
        typer.echo(f"  Missing terminal facts: {report.missing_terminal_facts}")
    if report.broken_dependency_refs:
        typer.echo("  Broken dependency references:")
        for ref in report.broken_dependency_refs:
            typer.echo(f"    {ref}")
    if report.ambiguous_facts:
        typer.echo("  Ambiguous facts (require human review):")
        for fid in report.ambiguous_facts:
            typer.echo(f"    ⚠ {fid}")
    if report.errors:
        typer.echo("  Errors:")
        for e in report.errors:
            typer.echo(f"    ✗ {e}")
    if report.warnings:
        typer.echo("  Warnings:")
        for w in report.warnings:
            typer.echo(f"    ! {w}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _print_validation(report: "ValidationReport") -> None:
    status = "VALID" if report.valid else "INVALID"
    typer.echo(f"  Status: {status}")
    if report.errors:
        for e in report.errors:
            typer.echo(f"  ✗ {e}")
    if report.ambiguous_facts:
        typer.echo(f"  Ambiguous facts requiring review: {report.ambiguous_facts}")


def _compute_total_cost() -> Optional[float]:
    cost_path = Path("data/cost_log.json")
    if not cost_path.exists():
        return None
    try:
        entries: list[dict] = json.loads(cost_path.read_text())  # type: ignore[type-arg]
        return sum(float(e.get("estimated_cost_usd", 0)) for e in entries)
    except Exception:
        return None


# Required for TYPE_CHECKING imports to work in function bodies
if sys.version_info >= (3, 11):
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from fact_graph.schema import FactGraph, ValidationReport
