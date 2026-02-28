"""
Hardcoded FEMA Individual Assistance Rental Assistance Fact Graph.

This fixture represents the complete eligibility logic derived from:
  - 44 CFR §206.110 (program overview, duplication of benefits, NFIP requirement)
  - 44 CFR §206.111 (definitions: displaced applicant, financial ability, etc.)
  - 44 CFR §206.113 (eligibility factors: NFIP restriction, flood insurance obligation)
  - 44 CFR §206.117(b)(1)(i) (rental assistance conditions and calculation)

No LLM calls are required to load this fixture. It is the ground truth for engine tests.
"""

from __future__ import annotations

from fact_graph.schema import (
    CFRCitation,
    Condition,
    ConditionOperator,
    FactGraph,
    FactNode,
    FactStatus,
    FactType,
)

# ---------------------------------------------------------------------------
# CFRCitation helpers (avoid repetition)
# ---------------------------------------------------------------------------

def _cite(section: str, paragraph: str | None, excerpt: str) -> CFRCitation:
    return CFRCitation(
        title=44,
        part=206,
        section=section,
        paragraph=paragraph,
        text_excerpt=excerpt,
    )


C110_B1 = _cite("206.110", "(b)(1)", "excludes rental assistance under § 206.117(b)(1)(i)")
C111_DISPLACED = _cite("206.111", None, "Displaced applicant means one whose disaster-damaged primary residence is uninhabitable, inaccessible, or made unavailable by the landlord.")
C111_FINANCIAL = _cite("206.111", None, "Financial ability means the applicant's capability to pay 30 percent of gross post-disaster household income for housing.")
C113_B7 = _cite("206.113", "(b)(7)", "may not provide assistance ... unless the community ... is participating in the NFIP")
C113_B8 = _cite("206.113", "(b)(8)", "did not fulfill the condition to purchase and maintain flood insurance as a requirement of receiving previous Federal disaster assistance")
C117_B1I = _cite("206.117", "(b)(1)(i)", "FEMA may provide financial assistance to individuals or households who are displaced applicants")
C117_B1IB = _cite("206.117", "(b)(1)(i)(B)", "housing costs exceed 30 percent of gross post-disaster household income")
C117_B1IC = _cite("206.117", "(b)(1)(i)(C)", "The primary residence was damaged by the disaster; uninhabitable, inaccessible, or made unavailable; applicant has a permanent housing plan.")
C110_H = _cite("206.110", "(h)", "FEMA will not provide assistance when any other source has already provided such assistance")

# ---------------------------------------------------------------------------
# Leaf (input) FactNodes — no dependencies, resolved by applicant intake form
# ---------------------------------------------------------------------------

LEAF_FACTS: list[FactNode] = [
    FactNode(
        id="primary_residence_damaged_by_disaster",
        label="Primary Residence Was Damaged by the Declared Disaster",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C117_B1IC],
    ),
    FactNode(
        id="primary_residence_is_uninhabitable",
        label="Primary Residence Is Uninhabitable (not safe or sanitary)",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C111_DISPLACED],
    ),
    FactNode(
        id="primary_residence_is_inaccessible",
        label="Primary Residence Is Inaccessible (access routes disrupted or blocked)",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C111_DISPLACED],
    ),
    FactNode(
        id="made_unavailable_by_landlord",
        label="Primary Residence Made Unavailable by the Landlord",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C111_DISPLACED],
    ),
    FactNode(
        id="has_permanent_housing_plan",
        label="Applicant Has a Permanent Housing Plan",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C117_B1IC],
    ),
    FactNode(
        id="gross_post_disaster_monthly_income",
        label="Gross Post-Disaster Household Monthly Income (dollars)",
        fact_type=FactType.NUMERIC,
        cfr_citations=[C111_FINANCIAL],
    ),
    FactNode(
        id="monthly_housing_cost",
        label="Applicant's Current Monthly Housing Cost (dollars)",
        fact_type=FactType.NUMERIC,
        cfr_citations=[C117_B1IB],
    ),
    FactNode(
        id="fair_market_rent_amount",
        label="HUD Fair Market Rent for Area (dollars/month) — external lookup required",
        fact_type=FactType.NUMERIC,
        cfr_citations=[_cite("206.117", "(b)(1)(i)(A)", "based on the fair market rent for the area as determined by HUD")],
        ambiguity_notes=(
            "Fair market rent is determined by HUD, not FEMA CFR. "
            "This is an external data dependency requiring lookup via HUD FMR database."
        ),
    ),
    FactNode(
        id="in_special_flood_hazard_area",
        label="Primary Residence in FEMA-Designated Special Flood Hazard Area",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C113_B7],
    ),
    FactNode(
        id="in_nfip_participating_community",
        label="Community Participates in the National Flood Insurance Program",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C113_B7],
    ),
    FactNode(
        id="insurance_covers_housing_need",
        label="Applicant's Insurance Covers the Housing Need (not significantly delayed, insufficient, or unusable)",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C110_H],
    ),
    FactNode(
        id="other_source_provides_assistance",
        label="Another Source Already Provides or Will Provide Equivalent Housing Assistance",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C110_H],
    ),
    FactNode(
        id="flood_insurance_previously_required",
        label="Flood Insurance Was Previously Required as a Condition of Federal Disaster Assistance",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C113_B8],
    ),
    FactNode(
        id="flood_insurance_previously_maintained",
        label="Required Flood Insurance Was Purchased and Maintained",
        fact_type=FactType.BOOLEAN,
        cfr_citations=[C113_B8],
    ),
]

# ---------------------------------------------------------------------------
# Derived FactNodes — resolved by the engine from their dependencies
# ---------------------------------------------------------------------------

DERIVED_FACTS: list[FactNode] = [
    # applicant_is_displaced — True if ANY habitability condition is met.
    FactNode(
        id="applicant_is_displaced",
        label="Applicant Is a Displaced Applicant",
        fact_type=FactType.BOOLEAN,
        dependencies=[
            "primary_residence_is_uninhabitable",
            "primary_residence_is_inaccessible",
            "made_unavailable_by_landlord",
        ],
        conditions=[
            Condition(
                operator=ConditionOperator.OR,
                operands=[
                    "primary_residence_is_uninhabitable",
                    "primary_residence_is_inaccessible",
                    "made_unavailable_by_landlord",
                ],
                result_value=True,
            )
        ],
        cfr_citations=[C111_DISPLACED],
    ),

    # thirty_pct_gross_income — 30% of monthly income (the financial ability threshold).
    FactNode(
        id="thirty_pct_gross_income",
        label="30% of Gross Post-Disaster Monthly Income (financial ability threshold)",
        fact_type=FactType.NUMERIC,
        dependencies=["gross_post_disaster_monthly_income"],
        conditions=[
            Condition(
                operator=ConditionOperator.MULTIPLY,
                operands=["gross_post_disaster_monthly_income", "0.3"],
                result_value=None,
            )
        ],
        cfr_citations=[C111_FINANCIAL],
    ),

    # applicant_has_financial_need — True when housing cost exceeds 30% of income.
    FactNode(
        id="applicant_has_financial_need",
        label="Applicant's Housing Cost Exceeds 30% of Gross Income (has financial need)",
        fact_type=FactType.BOOLEAN,
        dependencies=["monthly_housing_cost", "thirty_pct_gross_income"],
        conditions=[
            Condition(
                operator=ConditionOperator.GREATER_THAN,
                operands=["monthly_housing_cost", "thirty_pct_gross_income"],
                result_value=True,
            )
        ],
        cfr_citations=[C117_B1IB],
    ),

    # rental_shortfall_amount — the portion of rent FEMA can cover.
    # = fair_market_rent - thirty_pct_gross_income (cannot be negative in practice).
    FactNode(
        id="rental_shortfall_amount",
        label="Rental Assistance Amount (FMR minus 30% of income)",
        fact_type=FactType.NUMERIC,
        dependencies=["fair_market_rent_amount", "thirty_pct_gross_income"],
        conditions=[
            Condition(
                operator=ConditionOperator.SUBTRACT,
                operands=["fair_market_rent_amount", "thirty_pct_gross_income"],
                result_value=None,
            )
        ],
        cfr_citations=[C117_B1IB],
    ),

    # duplication_of_benefits_clear — True when no duplicative source exists.
    FactNode(
        id="duplication_of_benefits_clear",
        label="No Duplication of Benefits (no other source covers the need)",
        fact_type=FactType.BOOLEAN,
        dependencies=["other_source_provides_assistance", "insurance_covers_housing_need"],
        conditions=[
            Condition(
                operator=ConditionOperator.NOT,
                operands=[
                    Condition(
                        operator=ConditionOperator.OR,
                        operands=[
                            "other_source_provides_assistance",
                            "insurance_covers_housing_need",
                        ],
                        result_value=None,
                    )
                ],
                result_value=True,
            )
        ],
        cfr_citations=[C110_H],
    ),

    # nfip_restriction_applies — True when in SFHA and community NOT in NFIP.
    # Note: §206.113(b)(7) contains an exception allowing rental assistance even
    # in non-NFIP communities, which creates a conditional eligibility path.
    # This node models the base restriction; the exception is reflected in
    # applicant_eligible_for_rental_assistance conditions.
    FactNode(
        id="nfip_restriction_applies",
        label="NFIP Restriction Applies (in SFHA, community not in NFIP)",
        fact_type=FactType.BOOLEAN,
        dependencies=["in_special_flood_hazard_area", "in_nfip_participating_community"],
        conditions=[
            Condition(
                operator=ConditionOperator.AND,
                operands=[
                    "in_special_flood_hazard_area",
                    Condition(
                        operator=ConditionOperator.NOT,
                        operands=["in_nfip_participating_community"],
                        result_value=None,
                    ),
                ],
                result_value=True,
            )
        ],
        cfr_citations=[C113_B7],
        ambiguity_notes=(
            "§206.113(b)(7) contains an exception: rental assistance for alternate housing "
            "remains available even when NFIP restriction applies. This node models only the "
            "restriction; the exception path requires separate handling in "
            "applicant_eligible_for_rental_assistance."
        ),
    ),

    # previous_insurance_obligation_met — True when no prior obligation OR obligation was met.
    FactNode(
        id="previous_insurance_obligation_met",
        label="Previous Flood Insurance Obligation Met (or no prior obligation)",
        fact_type=FactType.BOOLEAN,
        dependencies=[
            "flood_insurance_previously_required",
            "flood_insurance_previously_maintained",
        ],
        conditions=[
            # If flood insurance was never required → obligation met (True).
            Condition(
                operator=ConditionOperator.NOT,
                operands=["flood_insurance_previously_required"],
                result_value=True,
            ),
            # If it was required AND was maintained → obligation met (True).
            Condition(
                operator=ConditionOperator.AND,
                operands=[
                    "flood_insurance_previously_required",
                    "flood_insurance_previously_maintained",
                ],
                result_value=True,
            ),
        ],
        cfr_citations=[C113_B8],
    ),
]

# ---------------------------------------------------------------------------
# Terminal FactNodes — the final determination outputs
# ---------------------------------------------------------------------------

TERMINAL_FACTS: list[FactNode] = [
    # applicant_eligible_for_rental_assistance — the primary determination.
    # All six conditions must hold per §206.117(b)(1)(i)(C), §206.110(h), §206.113.
    FactNode(
        id="applicant_eligible_for_rental_assistance",
        label="Applicant Is Eligible for FEMA Rental Assistance",
        fact_type=FactType.BOOLEAN,
        dependencies=[
            "primary_residence_damaged_by_disaster",
            "applicant_is_displaced",
            "has_permanent_housing_plan",
            "applicant_has_financial_need",
            "duplication_of_benefits_clear",
            "nfip_restriction_applies",
            "previous_insurance_obligation_met",
        ],
        conditions=[
            Condition(
                operator=ConditionOperator.AND,
                operands=[
                    "primary_residence_damaged_by_disaster",
                    "applicant_is_displaced",
                    "has_permanent_housing_plan",
                    "applicant_has_financial_need",
                    "duplication_of_benefits_clear",
                    Condition(
                        operator=ConditionOperator.NOT,
                        operands=["nfip_restriction_applies"],
                        result_value=None,
                    ),
                    "previous_insurance_obligation_met",
                ],
                result_value=True,
            )
        ],
        cfr_citations=[C117_B1IC, C110_H, C113_B7, C113_B8],
    ),

    # maximum_award_amount — the rental shortfall amount (FMR - 30% income).
    # Rental assistance is explicitly excluded from the $25k cap per §206.110(b)(1).
    FactNode(
        id="maximum_award_amount",
        label="Maximum Rental Assistance Award Amount (dollars/month)",
        fact_type=FactType.NUMERIC,
        dependencies=["rental_shortfall_amount"],
        conditions=[
            Condition(
                operator=ConditionOperator.MULTIPLY,
                operands=["rental_shortfall_amount", "1.0"],
                result_value=None,
            )
        ],
        cfr_citations=[
            C110_B1,
            _cite(
                "206.117",
                "(b)(1)(i)(A)",
                "based on the fair market rent for the area as determined by HUD",
            ),
        ],
        ambiguity_notes=(
            "The maximum monthly amount is based on HUD fair market rent minus 30% of income. "
            "The 18-month total period cap is a separate constraint not modeled here."
        ),
    ),
]

# ---------------------------------------------------------------------------
# Assemble the complete FactGraph
# ---------------------------------------------------------------------------

def build_fema_ia_graph() -> FactGraph:
    """
    Build and return the hardcoded FEMA IA Rental Assistance Fact Graph.

    This function is idempotent — call it as many times as needed.
    """
    all_nodes: list[FactNode] = LEAF_FACTS + DERIVED_FACTS + TERMINAL_FACTS
    nodes_dict = {node.id: node for node in all_nodes}

    return FactGraph(
        nodes=nodes_dict,
        terminal_fact_ids=[
            "applicant_eligible_for_rental_assistance",
            "maximum_award_amount",
        ],
        program="FEMA Individual Assistance — Rental Assistance",
    )


# Singleton for convenience in tests.
FEMA_IA_GRAPH = build_fema_ia_graph()
