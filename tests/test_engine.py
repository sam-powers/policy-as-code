"""
Engine unit tests using the hardcoded FEMA IA Fact Graph fixture.

All tests run fully offline — no API calls, no network access.

Scenarios:
  1. Clearly eligible: all conditions met → eligible=True, max_award computed
  2. Ineligible - not displaced: all habitability flags False → eligible=False
  3. Ineligible - NFIP restriction: in_sfha=True, in_nfip=False → eligible=False
  4. Incomplete: only one fact provided → eligible UNRESOLVED, unresolved_inputs non-empty
  5. Cycle detection: synthetic cycle → CycleError raised
  6. Forward propagation: two load+resolve passes → correct re-resolution
"""

from __future__ import annotations

import pytest

from fact_graph.engine import CycleError, FactGraphEngine
from fact_graph.schema import (
    CFRCitation,
    Condition,
    ConditionOperator,
    FactGraph,
    FactNode,
    FactStatus,
    FactType,
)
from tests.fixtures.fema_ia_graph import build_fema_ia_graph

# ---------------------------------------------------------------------------
# Common input sets
# ---------------------------------------------------------------------------

ELIGIBLE_INPUTS = {
    "primary_residence_damaged_by_disaster": True,
    "primary_residence_is_uninhabitable": True,
    "primary_residence_is_inaccessible": False,
    "made_unavailable_by_landlord": False,
    "has_permanent_housing_plan": True,
    "gross_post_disaster_monthly_income": 2000.0,
    "monthly_housing_cost": 1200.0,
    "fair_market_rent_amount": 1500.0,
    "in_special_flood_hazard_area": False,
    "in_nfip_participating_community": True,
    "insurance_covers_housing_need": False,
    "other_source_provides_assistance": False,
    "flood_insurance_previously_required": False,
    "flood_insurance_previously_maintained": False,
}


# ---------------------------------------------------------------------------
# Scenario 1: Clearly eligible
# ---------------------------------------------------------------------------

def test_clearly_eligible() -> None:
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(ELIGIBLE_INPUTS)
    engine.resolve()
    det = engine.get_determination()

    # Terminal: eligible
    eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    assert eligible_trace is not None, "Terminal fact should be in determination"
    assert eligible_trace.status == FactStatus.RESOLVED
    assert eligible_trace.value is True

    # Terminal: max award = FMR - 30% of income = 1500 - 600 = 900
    award_trace = det.terminal_facts.get("maximum_award_amount")
    assert award_trace is not None
    assert award_trace.status == FactStatus.RESOLVED
    assert award_trace.value == pytest.approx(900.0)

    # No unresolved inputs
    assert det.unresolved_inputs == [], f"Unexpected unresolved inputs: {det.unresolved_inputs}"


def test_clearly_eligible_traces_cfr_citations() -> None:
    """Every resolved terminal fact must carry CFR citations."""
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(ELIGIBLE_INPUTS)
    engine.resolve()
    det = engine.get_determination()

    eligible_trace = det.terminal_facts["applicant_eligible_for_rental_assistance"]
    assert len(eligible_trace.cfr_citations) > 0, "Terminal fact must have CFR citations"


# ---------------------------------------------------------------------------
# Scenario 2: Ineligible — not displaced
# ---------------------------------------------------------------------------

def test_ineligible_not_displaced() -> None:
    inputs = {**ELIGIBLE_INPUTS}
    inputs["primary_residence_is_uninhabitable"] = False
    inputs["primary_residence_is_inaccessible"] = False
    inputs["made_unavailable_by_landlord"] = False

    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(inputs)
    engine.resolve()
    det = engine.get_determination()

    # applicant_is_displaced should be False
    disp_trace = engine.get_trace("applicant_is_displaced")
    assert disp_trace.status == FactStatus.RESOLVED
    assert disp_trace.value is False

    # Terminal eligibility should be False (AND short-circuit)
    eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    assert eligible_trace is not None
    assert eligible_trace.status == FactStatus.RESOLVED
    assert eligible_trace.value is False


# ---------------------------------------------------------------------------
# Scenario 3: Ineligible — NFIP restriction
# ---------------------------------------------------------------------------

def test_ineligible_nfip_restriction() -> None:
    inputs = {**ELIGIBLE_INPUTS}
    inputs["in_special_flood_hazard_area"] = True
    inputs["in_nfip_participating_community"] = False

    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(inputs)
    engine.resolve()
    det = engine.get_determination()

    nfip_trace = engine.get_trace("nfip_restriction_applies")
    assert nfip_trace.status == FactStatus.RESOLVED
    assert nfip_trace.value is True

    eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    assert eligible_trace is not None
    assert eligible_trace.status == FactStatus.RESOLVED
    assert eligible_trace.value is False


# ---------------------------------------------------------------------------
# Scenario 4: Incomplete — only one fact provided
# ---------------------------------------------------------------------------

def test_incomplete_single_fact() -> None:
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts({"primary_residence_damaged_by_disaster": True})
    engine.resolve()
    det = engine.get_determination()

    # Terminal should not be in terminal_facts (still unresolved)
    eligible_trace = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    # It may be absent (unresolved) or present with UNRESOLVED status.
    if eligible_trace is not None:
        assert eligible_trace.status in (FactStatus.UNRESOLVED, FactStatus.UNKNOWN)

    # Many leaf inputs should be missing.
    assert len(det.unresolved_inputs) > 5, (
        f"Expected many unresolved inputs, got: {det.unresolved_inputs}"
    )

    # The engine's get_unresolved_inputs() should return leaf nodes still UNKNOWN.
    unresolved = engine.get_unresolved_inputs()
    assert len(unresolved) > 0
    # All returned nodes should have no dependencies (they are leaf facts).
    for node in unresolved:
        assert node.dependencies == [], f"{node.id} has dependencies but was returned as unresolved input"


def test_incomplete_no_error_on_missing_inputs() -> None:
    """Engine must never raise on missing inputs — partial resolution is allowed."""
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    # Provide no inputs at all.
    engine.load_facts({})
    # Should not raise.
    engine.resolve()
    det = engine.get_determination()
    # Every leaf fact should be in unresolved_inputs.
    assert len(det.unresolved_inputs) >= 14


# ---------------------------------------------------------------------------
# Scenario 5: Cycle detection
# ---------------------------------------------------------------------------

def test_cycle_detection_raises() -> None:
    """A graph with a dependency cycle must raise CycleError at engine init."""
    cite = CFRCitation(
        title=44, part=206, section="206.110", paragraph=None, text_excerpt="test"
    )
    node_a = FactNode(
        id="fact_a",
        label="Fact A",
        fact_type=FactType.BOOLEAN,
        dependencies=["fact_b"],
        conditions=[
            Condition(operator=ConditionOperator.EQUALS, operands=["fact_b", "true"], result_value=True)
        ],
        cfr_citations=[cite],
    )
    node_b = FactNode(
        id="fact_b",
        label="Fact B",
        fact_type=FactType.BOOLEAN,
        dependencies=["fact_a"],
        conditions=[
            Condition(operator=ConditionOperator.EQUALS, operands=["fact_a", "true"], result_value=True)
        ],
        cfr_citations=[cite],
    )
    cyclic_graph = FactGraph(
        nodes={"fact_a": node_a, "fact_b": node_b},
        terminal_fact_ids=["fact_a"],
    )
    with pytest.raises((CycleError, ValueError)):
        FactGraphEngine(cyclic_graph)


def test_self_reference_cycle() -> None:
    """A self-referential dependency must also raise CycleError."""
    cite = CFRCitation(
        title=44, part=206, section="206.110", paragraph=None, text_excerpt="test"
    )
    node = FactNode(
        id="fact_self",
        label="Self",
        fact_type=FactType.BOOLEAN,
        dependencies=["fact_self"],
        conditions=[],
        cfr_citations=[cite],
    )
    cyclic_graph = FactGraph(
        nodes={"fact_self": node},
        terminal_fact_ids=["fact_self"],
    )
    with pytest.raises((CycleError, ValueError)):
        FactGraphEngine(cyclic_graph)


# ---------------------------------------------------------------------------
# Scenario 6: Forward propagation
# ---------------------------------------------------------------------------

def test_forward_propagation() -> None:
    """
    Providing facts in two separate load_facts calls must correctly re-resolve
    downstream facts. Facts resolved in the first pass that gain new dependencies
    satisfied by the second pass must be updated.
    """
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)

    # First pass: provide only habitability facts.
    engine.load_facts({
        "primary_residence_is_uninhabitable": True,
        "primary_residence_is_inaccessible": False,
        "made_unavailable_by_landlord": False,
    })
    engine.resolve()

    # applicant_is_displaced should already be True (OR fired).
    disp_trace = engine.get_trace("applicant_is_displaced")
    assert disp_trace.status == FactStatus.RESOLVED
    assert disp_trace.value is True

    # Terminal should still be UNRESOLVED (many deps missing).
    det_1 = engine.get_determination()
    assert "applicant_eligible_for_rental_assistance" not in det_1.terminal_facts

    # Second pass: provide remaining facts.
    engine.load_facts({
        "primary_residence_damaged_by_disaster": True,
        "has_permanent_housing_plan": True,
        "gross_post_disaster_monthly_income": 3000.0,
        "monthly_housing_cost": 1400.0,
        "fair_market_rent_amount": 1800.0,
        "in_special_flood_hazard_area": False,
        "in_nfip_participating_community": True,
        "insurance_covers_housing_need": False,
        "other_source_provides_assistance": False,
        "flood_insurance_previously_required": False,
        "flood_insurance_previously_maintained": False,
    })
    engine.resolve()

    det_2 = engine.get_determination()
    eligible_trace = det_2.terminal_facts.get("applicant_eligible_for_rental_assistance")
    assert eligible_trace is not None
    assert eligible_trace.status == FactStatus.RESOLVED
    assert eligible_trace.value is True

    # max_award = 1800 - (3000 * 0.3) = 1800 - 900 = 900
    award_trace = det_2.terminal_facts.get("maximum_award_amount")
    assert award_trace is not None
    assert award_trace.value == pytest.approx(900.0)


# ---------------------------------------------------------------------------
# Additional: provenance text rendering
# ---------------------------------------------------------------------------

def test_determination_text_rendering() -> None:
    """format_determination_text should produce non-empty output without errors."""
    from fact_graph.provenance import format_determination_text

    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(ELIGIBLE_INPUTS)
    engine.resolve()
    det = engine.get_determination()
    text = format_determination_text(det)
    assert "DETERMINATION:" in text
    assert "ELIGIBLE" in text


def test_trace_text_rendering() -> None:
    """format_trace_text should produce non-empty output without errors."""
    from fact_graph.provenance import format_trace_text

    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(ELIGIBLE_INPUTS)
    engine.resolve()
    trace = engine.get_trace("applicant_is_displaced")
    text = format_trace_text(trace)
    assert "applicant_is_displaced" in text
    assert "44 CFR" in text


# ---------------------------------------------------------------------------
# Additional: previous_insurance_obligation_met logic
# ---------------------------------------------------------------------------

def test_previous_insurance_obligation_never_required() -> None:
    """When flood insurance was never required, obligation is met."""
    inputs = {**ELIGIBLE_INPUTS, "flood_insurance_previously_required": False}
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(inputs)
    engine.resolve()
    trace = engine.get_trace("previous_insurance_obligation_met")
    assert trace.status == FactStatus.RESOLVED
    assert trace.value is True


def test_previous_insurance_obligation_required_not_maintained() -> None:
    """When required but not maintained → obligation NOT met → ineligible."""
    inputs = {
        **ELIGIBLE_INPUTS,
        "flood_insurance_previously_required": True,
        "flood_insurance_previously_maintained": False,
    }
    graph = build_fema_ia_graph()
    engine = FactGraphEngine(graph)
    engine.load_facts(inputs)
    engine.resolve()

    trace = engine.get_trace("previous_insurance_obligation_met")
    assert trace.status == FactStatus.RESOLVED
    assert trace.value is False

    det = engine.get_determination()
    eligible = det.terminal_facts.get("applicant_eligible_for_rental_assistance")
    assert eligible is not None
    assert eligible.value is False
