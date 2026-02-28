"""Pydantic models for the Fact Graph schema."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field

# Type alias for fact values — covers all concrete types used in this domain.
FactValue = Union[bool, int, float, str, None]


class FactType(str, Enum):
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    NUMERIC = "numeric"
    DATE = "date"


class FactStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class ConditionOperator(str, Enum):
    # Logical
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    # Comparison
    EQUALS = "EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    IN = "IN"
    # Arithmetic — operands are [fact_id_or_literal, ...]; result_value=None (computed at runtime)
    MULTIPLY = "MULTIPLY"
    SUBTRACT = "SUBTRACT"
    ADD = "ADD"


class CFRCitation(BaseModel):
    title: int
    part: int
    section: str
    paragraph: Union[str, None] = None
    text_excerpt: str


class Condition(BaseModel):
    """
    A single condition node in the rule DSL.

    operands: list of fact IDs (str) or nested Condition objects.
    result_value: the value the parent FactNode resolves to when this condition fires.
                  For arithmetic operators (MULTIPLY, SUBTRACT, ADD), result_value is
                  None — the engine computes the value at runtime.
    """

    model_config = ConfigDict(arbitrary_types_allowed=False)

    operator: ConditionOperator
    operands: list[Union[str, "Condition"]]
    result_value: FactValue = None


# Required for the self-referential forward reference to resolve at runtime.
Condition.model_rebuild()


class FactNode(BaseModel):
    id: str
    label: str
    fact_type: FactType
    dependencies: list[str] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    cfr_citations: list[CFRCitation] = Field(default_factory=list)
    ambiguity_notes: Union[str, None] = None
    status: FactStatus = FactStatus.UNKNOWN
    value: FactValue = None


class FactGraph(BaseModel):
    """
    A complete collection of FactNodes with designated terminal (output) facts.

    terminal_fact_ids: IDs of facts that represent the final determination outputs,
    e.g. ["applicant_eligible_for_rental_assistance", "maximum_award_amount"].
    """

    nodes: dict[str, FactNode]
    terminal_fact_ids: list[str]
    program: str = "FEMA Individual Assistance — Rental Assistance"


# ---------------------------------------------------------------------------
# Resolution output models (not in spec; required by engine and CLI)
# ---------------------------------------------------------------------------


class ConditionFired(BaseModel):
    """Records which condition index matched and what value it produced."""

    condition_index: int
    operator: ConditionOperator
    result_value: FactValue


class ResolutionTrace(BaseModel):
    """Full audit trail for a single resolved fact."""

    fact_id: str
    label: str
    fact_type: FactType
    value: FactValue
    status: FactStatus
    conditions_fired: list[ConditionFired] = Field(default_factory=list)
    cfr_citations: list[CFRCitation] = Field(default_factory=list)
    # IDs of facts this fact depended on, and their values at resolution time.
    dependency_ids: list[str] = Field(default_factory=list)
    dependency_values: dict[str, FactValue] = Field(default_factory=dict)


class Determination(BaseModel):
    """Final determination output from the engine."""

    program: str
    scenario_label: Union[str, None] = None
    input_facts: dict[str, FactValue]
    # Terminal facts with their full resolution traces.
    terminal_facts: dict[str, ResolutionTrace]
    # All resolved derived facts.
    resolved_facts: dict[str, ResolutionTrace]
    # IDs of derived facts still UNRESOLVED (blocked upstream).
    unresolved_facts: list[str]
    # IDs of facts flagged AMBIGUOUS by the translation agent.
    ambiguous_facts: list[str]
    # Leaf fact IDs that have never been provided (engine is waiting on them).
    unresolved_inputs: list[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExternalReference(BaseModel):
    """Statutory or external references the discovery agent cannot chase."""

    citation: str          # e.g. "42 U.S.C. 5174"
    description: str
    reference_type: str    # "statutory" | "external_data"


class CFRManifestEntry(BaseModel):
    title: int
    section: str
    relevant: bool
    reason: str
    cross_references: list[str] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)
    last_fetched: str       # ISO date string
    cache_key: str


class CFRManifest(BaseModel):
    fetched_sections: list[CFRManifestEntry] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)
    fetch_date: str


class ValidationReport(BaseModel):
    """Output of post-translation schema validation."""

    valid: bool
    terminal_facts_present: bool
    missing_terminal_facts: list[str] = Field(default_factory=list)
    broken_dependency_refs: list[str] = Field(default_factory=list)
    ambiguous_facts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    """A synthetic applicant scenario for the test suite."""

    # Prevent pytest from treating this Pydantic model as a test class.
    __test__ = False

    id: str
    description: str
    inputs: dict[str, Any]
    expected_determination: str    # "eligible" | "ineligible" | "incomplete"
    expected_terminal_facts: dict[str, Any]
    rationale: str
