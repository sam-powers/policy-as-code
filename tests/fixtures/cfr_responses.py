"""
Mock eCFR API responses for offline tests.

Text is taken verbatim from Appendix A of the project specification,
which contains real CFR text current through 12/31/2024.

Real API response structure:
{
    "meta": {
        "cfr_reference": {"title": 44, "part": 206, "section": "206.113"},
        "date": "2026-02-28",
        "last_amended": "2024-12-31"
    },
    "content": "<full section text>"
}
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 44 CFR § 206.110 — Federal assistance to individuals and households
# ---------------------------------------------------------------------------

CFR_44_206_110 = {
    "meta": {
        "cfr_reference": {"title": 44, "part": 206, "section": "206.110"},
        "date": "2026-02-28",
        "last_amended": "2024-12-31",
    },
    "content": (
        "44 CFR § 206.110 — Federal assistance to individuals and households\n\n"
        "(a) Purpose. This section implements the policy and procedures set forth in the "
        "Robert T. Stafford Disaster Relief and Emergency Assistance Act, as amended "
        "(Stafford Act), 42 U.S.C. 5174. This program provides financial assistance and, "
        "if necessary, direct assistance to eligible individuals and households who, as a "
        "direct result of a major disaster or emergency, have uninsured or under-insured, "
        "necessary expenses and serious needs and are unable to meet such expenses or needs "
        "through other means.\n\n"
        "(b) Maximum amount of assistance. No individual or household will receive financial "
        "assistance greater than $25,000 under this subpart with respect to a single major "
        "disaster or emergency for the repair or replacement of their pre-disaster primary "
        "residence. No individual or household will receive financial assistance greater than "
        "$25,000 under this subpart with respect to a single major disaster or emergency for "
        "Other Needs Assistance. FEMA will adjust the $25,000 limits annually to reflect "
        "changes in the Consumer Price Index (CPI) for All Urban Consumers that the "
        "Department of Labor publishes.\n\n"
        "(1) The maximum amount of financial assistance excludes rental assistance under "
        "§ 206.117(b)(1)(i) and lodging expense reimbursement under § 206.117(b)(1)(i).\n\n"
        "(2) The maximum amount of financial assistance excludes expenses to repair or "
        "replace eligible damaged accessibility-related real property improvements and "
        "personal property for individuals with disabilities.\n\n"
        "(c) Multiple types of assistance. One or more types of housing assistance may be "
        "made available under this section to meet the needs of individuals and households "
        "in the particular disaster situation. An applicant is expected to accept the first "
        "offer of housing assistance; unwarranted refusal of assistance may result in the "
        "forfeiture of future housing assistance. Temporary housing and repair assistance "
        "must be utilized to the fullest extent practicable before other types of housing "
        "assistance.\n\n"
        "(d) Date of eligibility. Eligibility for Federal assistance under this subpart is "
        "limited to losses or expenses resulting from damage that occurred during the dates "
        "of the incident period established in a presidential declaration that a major "
        "disaster or emergency exists, except that reasonable lodging expenses that are "
        "incurred in anticipation of and immediately preceding such event may be eligible.\n\n"
        "(e) Period of assistance. FEMA may provide assistance under this subpart for a "
        "period not to exceed 18 months from the date of declaration. The Assistant "
        "Administrator for the Recovery Directorate may extend the period of assistance "
        "if he/she determines that due to extraordinary circumstances an extension would "
        "be in the public interest.\n\n"
        "(h) Duplication of benefits. In accordance with the requirements of the Stafford "
        "Act, 42 U.S.C. 5155, FEMA will not provide assistance under this subpart when any "
        "other source has already provided such assistance or when such assistance is "
        "available from any other source. In the instance of insured applicants, we will "
        "provide assistance under this subpart only when: (1) Payment of the applicable "
        "benefits are significantly delayed; (2) Applicable benefits are insufficient to "
        "cover the housing or other needs; or (3) Applicants cannot use their insurance "
        "because there is no housing on the private market.\n\n"
        "(k) Flood Disaster Protection Act requirement. Individuals or households that are "
        "located in a special flood hazard area may not receive Federal Assistance for "
        "NFIP-insurable real and/or personal property, damaged by a flood, unless the "
        "community in which the property is located is participating in the NFIP "
        "(See 44 CFR 59.1), or the exception in 42 U.S.C. 4105(d) applies."
    ),
}

# ---------------------------------------------------------------------------
# 44 CFR § 206.111 — Definitions
# ---------------------------------------------------------------------------

CFR_44_206_111 = {
    "meta": {
        "cfr_reference": {"title": 44, "part": 206, "section": "206.111"},
        "date": "2026-02-28",
        "last_amended": "2024-12-31",
    },
    "content": (
        "44 CFR § 206.111 — Definitions\n\n"
        "Adequate, alternate housing means housing that accommodates the needs of the "
        "occupants; is within the normal commuting patterns of the area or is within "
        "reasonable commuting distance of work, school, or agricultural activities that "
        "provide over 50 percent of the household income; and is within the financial "
        "ability of the occupant.\n\n"
        "Applicant means an individual or household who has applied for assistance under "
        "this subpart.\n\n"
        "Dependent means someone who is normally claimed as such on the Federal tax return "
        "of another, according to the Internal Revenue Code. It may also mean the minor "
        "children of a couple not living together, where the children live in the affected "
        "residence with the parent or guardian who does not claim them on the tax return.\n\n"
        "Destroyed means the primary residence is a total loss or damaged to such an extent "
        "that repairs are infeasible.\n\n"
        "Displaced applicant means one whose disaster-damaged primary residence is "
        "uninhabitable, inaccessible, or made unavailable by the landlord.\n\n"
        "Fair market rent means estimates of rent plus the cost of utilities, except "
        "telephone, identified by the Department of Housing and Urban Development as being "
        "adequate for existing rental housing in a particular geographic area.\n\n"
        "Financial ability means the applicant's capability to pay 30 percent of gross "
        "post-disaster household income for housing. When computing financial ability, "
        "extreme or unusual financial circumstances may be considered by FEMA.\n\n"
        "Household means all persons (adults and children) who lived in the pre-disaster "
        "residence who request assistance under this subpart, as well as any persons, such "
        "as infants, spouse, or part-time residents who were not present at the time of the "
        "disaster, but who are expected to return during the assistance period.\n\n"
        "Inaccessible means as a result of the incident, the applicant cannot reasonably be "
        "expected to gain entry to his or her pre-disaster residence due to the disruption, "
        "or destruction, of access routes or other impediments to access, or restrictions "
        "placed on movement by a responsible official due to continued health, safety or "
        "security problems.\n\n"
        "Permanent housing plan means a realistic plan that, within a reasonable timeframe, "
        "puts the displaced applicant back into permanent housing that is similar to their "
        "pre-disaster housing situation.\n\n"
        "Primary residence means the dwelling where the applicant normally lives, during the "
        "major portion of the calendar year; or the dwelling that is required because of "
        "proximity to employment, including agricultural activities, that provide 50 percent "
        "of the household's income.\n\n"
        "Significantly delayed means the process has taken more than 30 days.\n\n"
        "Uninhabitable means the dwelling is not safe or sanitary."
    ),
}

# ---------------------------------------------------------------------------
# 44 CFR § 206.113 — Eligibility factors
# ---------------------------------------------------------------------------

CFR_44_206_113 = {
    "meta": {
        "cfr_reference": {"title": 44, "part": 206, "section": "206.113"},
        "date": "2026-02-28",
        "last_amended": "2024-12-31",
    },
    "content": (
        "44 CFR § 206.113 — Eligibility factors\n\n"
        "(a) Conditions of eligibility. In general, FEMA may provide assistance to "
        "individuals and households who qualify for such assistance under the Stafford Act, "
        "42 U.S.C. 5174, and this subpart.\n\n"
        "(b) Ineligibility. FEMA may not provide assistance under this subpart:\n\n"
        "(7) To individuals or households whose damaged primary residence is located in a "
        "designated special flood hazard area, and in a community that is not participating "
        "in the National Flood Insurance Program, except that financial assistance may be "
        "provided to rent alternate housing and for medical, dental, funeral expenses and "
        "uninsurable items to such individuals or households. However, if the community in "
        "which the damaged property is located qualifies for and enters the NFIP during the "
        "six-month period following the declaration then the individual or household may be "
        "eligible;\n\n"
        "(8) To individuals or households who did not fulfill the condition to purchase and "
        "maintain flood insurance as a requirement of receiving previous Federal disaster "
        "assistance;\n\n"
        "(9) For business losses, including farm businesses; or\n\n"
        "(10) For any items not otherwise authorized by §§ 206.117 and 206.119."
    ),
}

# ---------------------------------------------------------------------------
# 44 CFR § 206.117 — Housing assistance (rental assistance excerpts)
# ---------------------------------------------------------------------------

CFR_44_206_117 = {
    "meta": {
        "cfr_reference": {"title": 44, "part": 206, "section": "206.117"},
        "date": "2026-02-28",
        "last_amended": "2024-12-31",
    },
    "content": (
        "44 CFR § 206.117 — Housing assistance (rental assistance excerpts)\n\n"
        "(b)(1)(i) Rental assistance. FEMA may provide financial assistance to individuals "
        "or households who are displaced applicants or whose primary residence was rendered "
        "inaccessible or uninhabitable as a result of the disaster. Financial assistance may "
        "be provided to rent alternate housing resources, including apartments, houses, "
        "manufactured housing, recreational vehicles, or other readily fabricated dwellings.\n\n"
        "(b)(1)(i)(A) Rental assistance will be provided based on the fair market rent for "
        "the area as determined by HUD. FEMA will provide this assistance for the period of "
        "time needed to repair or replace the damaged primary residence, not to exceed 18 "
        "months from the date of declaration.\n\n"
        "(b)(1)(i)(B) FEMA will consider the financial ability of the applicant when "
        "providing rental assistance. If an applicant has financial resources available, "
        "FEMA may provide rental assistance only to the extent that the applicant's housing "
        "costs exceed 30 percent of gross post-disaster household income.\n\n"
        "(b)(1)(i)(C) To receive rental assistance, the applicant must demonstrate that:\n"
        "* The primary residence was damaged by the disaster;\n"
        "* The primary residence is uninhabitable, inaccessible, or made unavailable by "
        "the landlord as a result of the disaster;\n"
        "* The applicant is a displaced applicant; and\n"
        "* The applicant has a permanent housing plan.\n\n"
        "(b)(1)(i)(D) Rental assistance may be extended in 3-month increments upon "
        "recertification that the applicant continues to meet the eligibility criteria. "
        "The maximum period for rental assistance is 18 months from the date of declaration.\n\n"
        "(b)(1)(i)(E) Applicants that receive displacement assistance under § 206.119(b)(2) "
        "must request rental assistance if their disaster-caused temporary housing needs "
        "continue once displacement assistance is exhausted.\n\n"
        "(b)(1)(ii) Direct housing. FEMA may provide direct assistance in the form of "
        "purchased or leased temporary housing units directly to displaced applicants who "
        "lack available housing resources and are unable to make use of the assistance "
        "provided under paragraph (b)(1)(i) of this section."
    ),
}

# ---------------------------------------------------------------------------
# eCFR Structure API response for Part 206 Subpart D
# ---------------------------------------------------------------------------

ECFR_STRUCTURE_PART_206 = {
    "identifier": "206",
    "label": "Part 206",
    "children": [
        {
            "identifier": "D",
            "label": "Subpart D—Federal Assistance to Individuals and Households",
            "children": [
                {
                    "identifier": "206.110",
                    "label": "Federal assistance to individuals and households.",
                },
                {"identifier": "206.111", "label": "Definitions."},
                {"identifier": "206.112", "label": "Registration period."},
                {"identifier": "206.113", "label": "Eligibility factors."},
                {"identifier": "206.114", "label": "Criteria for continued or additional assistance."},
                {"identifier": "206.115", "label": "Appeals."},
                {"identifier": "206.117", "label": "Housing assistance."},
                {"identifier": "206.118", "label": "Housing construction standards."},
                {"identifier": "206.119", "label": "Financial assistance to address other needs."},
                {"identifier": "206.120", "label": "State administration of the Individuals and Households Program."},
            ],
        }
    ],
}

# ---------------------------------------------------------------------------
# Convenience mapping: section string → mock response dict
# ---------------------------------------------------------------------------

SECTION_RESPONSES: dict[str, dict] = {  # type: ignore[type-arg]
    "206.110": CFR_44_206_110,
    "206.111": CFR_44_206_111,
    "206.113": CFR_44_206_113,
    "206.117": CFR_44_206_117,
}
