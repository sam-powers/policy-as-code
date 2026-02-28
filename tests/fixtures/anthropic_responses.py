"""
Mock Anthropic API responses for offline tests.

Uses anthropic.types.Message.model_construct() to build response objects
without any network calls or API validation.

These mocks reflect what the real API would return for:
1. Discovery relevance check (§206.113 example)
2. Translation of §206.113 into FactNode definitions
"""

from __future__ import annotations

import json

import anthropic

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(text: str) -> anthropic.types.Message:
    """Construct a mock anthropic.types.Message with a single text block."""
    content_block = anthropic.types.TextBlock(type="text", text=text)
    usage = anthropic.types.Usage(input_tokens=500, output_tokens=200)
    return anthropic.types.Message.model_construct(
        id="msg_mock_000",
        type="message",
        role="assistant",
        content=[content_block],
        model="claude-sonnet-4-20250514",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Mock: Discovery relevance check for §206.113
# ---------------------------------------------------------------------------

RELEVANCE_RESPONSE_RELEVANT = _make_message(
    json.dumps({
        "relevant": True,
        "reason": (
            "§206.113 contains eligibility conditions including the NFIP special flood "
            "hazard area restriction and the flood insurance maintenance requirement, "
            "both directly applicable to rental assistance eligibility for flood-displaced "
            "applicants."
        ),
        "cross_references": [
            "206.117",
            "206.119",
            "59.1",
        ],
    })
)

RELEVANCE_RESPONSE_NOT_RELEVANT = _make_message(
    json.dumps({
        "relevant": False,
        "reason": "This section addresses registration periods and does not contain eligibility conditions relevant to rental assistance.",
        "cross_references": [],
    })
)

# ---------------------------------------------------------------------------
# Mock: Translation of §206.113 into FactNode definitions
# ---------------------------------------------------------------------------

_TRANSLATION_NODES = [
    {
        "id": "in_special_flood_hazard_area",
        "label": "Primary Residence in Special Flood Hazard Area",
        "fact_type": "boolean",
        "dependencies": [],
        "conditions": [],
        "cfr_citations": [
            {
                "title": 44,
                "part": 206,
                "section": "206.113",
                "paragraph": "(b)(7)",
                "text_excerpt": (
                    "individuals or households whose damaged primary residence is located "
                    "in a designated special flood hazard area"
                ),
            }
        ],
        "ambiguity_notes": None,
        "status": "unknown",
        "value": None,
    },
    {
        "id": "in_nfip_participating_community",
        "label": "Community Participates in NFIP",
        "fact_type": "boolean",
        "dependencies": [],
        "conditions": [],
        "cfr_citations": [
            {
                "title": 44,
                "part": 206,
                "section": "206.113",
                "paragraph": "(b)(7)",
                "text_excerpt": (
                    "a community that is not participating in the National Flood Insurance Program"
                ),
            }
        ],
        "ambiguity_notes": None,
        "status": "unknown",
        "value": None,
    },
    {
        "id": "nfip_restriction_applies",
        "label": "NFIP Restriction Applies (SFHA + Non-Participating Community)",
        "fact_type": "boolean",
        "dependencies": ["in_special_flood_hazard_area", "in_nfip_participating_community"],
        "conditions": [
            {
                "operator": "AND",
                "operands": [
                    "in_special_flood_hazard_area",
                    {
                        "operator": "NOT",
                        "operands": ["in_nfip_participating_community"],
                        "result_value": None,
                    },
                ],
                "result_value": True,
            }
        ],
        "cfr_citations": [
            {
                "title": 44,
                "part": 206,
                "section": "206.113",
                "paragraph": "(b)(7)",
                "text_excerpt": (
                    "may not provide assistance ... unless the community ... is participating in the NFIP"
                ),
            }
        ],
        "ambiguity_notes": (
            "§206.113(b)(7) contains an exception: rental assistance may still be provided "
            "even in non-NFIP communities. This creates a conditional eligibility path that "
            "requires careful dependency mapping."
        ),
        "status": "unknown",
        "value": None,
    },
    {
        "id": "flood_insurance_previously_required",
        "label": "Flood Insurance Previously Required as Disaster Assistance Condition",
        "fact_type": "boolean",
        "dependencies": [],
        "conditions": [],
        "cfr_citations": [
            {
                "title": 44,
                "part": 206,
                "section": "206.113",
                "paragraph": "(b)(8)",
                "text_excerpt": (
                    "did not fulfill the condition to purchase and maintain flood insurance "
                    "as a requirement of receiving previous Federal disaster assistance"
                ),
            }
        ],
        "ambiguity_notes": None,
        "status": "unknown",
        "value": None,
    },
    {
        "id": "flood_insurance_previously_maintained",
        "label": "Flood Insurance Was Purchased and Maintained as Required",
        "fact_type": "boolean",
        "dependencies": [],
        "conditions": [],
        "cfr_citations": [
            {
                "title": 44,
                "part": 206,
                "section": "206.113",
                "paragraph": "(b)(8)",
                "text_excerpt": (
                    "fulfill the condition to purchase and maintain flood insurance"
                ),
            }
        ],
        "ambiguity_notes": None,
        "status": "unknown",
        "value": None,
    },
]

TRANSLATION_RESPONSE = _make_message(json.dumps(_TRANSLATION_NODES))

# ---------------------------------------------------------------------------
# Convenience: factory for custom mock responses
# ---------------------------------------------------------------------------

def make_relevance_response(relevant: bool, reason: str, cross_refs: list[str]) -> anthropic.types.Message:
    return _make_message(
        json.dumps({"relevant": relevant, "reason": reason, "cross_references": cross_refs})
    )
