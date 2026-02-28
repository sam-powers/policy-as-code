# Disaster Assistance Fact Graph

A pilot system for translating federal benefit eligibility rules into executable, auditable determination logic — starting with FEMA Individual Assistance rental assistance for flood-displaced applicants.

## The Problem

Federal benefit eligibility rules live in the Code of Federal Regulations (CFR) — written in natural language for lawyers, cross-referencing hundreds of sections across multiple titles. Translating that into working software currently takes policy analysts and engineers weeks per program. The logic is often re-implemented inconsistently across agencies, contains silent interpretive choices, and is nearly impossible to audit.

The result: people who are eligible for help don't get it, and nobody can easily explain why.

## The Approach

This system uses AI agents to do the translation work — reading CFR text, extracting eligibility logic, resolving cross-references, and producing a structured **Fact Graph**: a declarative dependency graph where every fact about an applicant has explicit dependencies, structured conditions, and a traceable citation back to the CFR.

The Fact Graph engine then takes applicant inputs and propagates them through the graph, resolving eligibility incrementally as information becomes available. Partial information is a first-class concept — the system surfaces what it knows, what it's still waiting for, and where the rules are genuinely ambiguous.

This architecture was pioneered by the IRS Direct File project (built with USDS) for tax determination. This pilot extends it to disaster assistance benefits.

## Why This Matters

The determination layer — knowing who is eligible, for what, in what amount — is where the policy complexity and inequity live. Payment systems are a solved problem. The determination layer is not.

A modernized determination layer produces a clean, auditable output that:
- Legacy payment infrastructure can consume without being replaced
- Policy experts can review without reading code
- Courts and oversight bodies can audit with full provenance
- Can be shared across programs so a survivor describes what happened to them once, and eligibility resolves across FEMA, SBA, state programs, and others in parallel

## Pilot Scope

This pilot is intentionally narrow:

- **Program:** FEMA Individual Assistance (IA)
- **Disaster type:** Flood
- **Benefit:** Rental assistance for displaced applicants
- **CFR scope:** 44 CFR Part 206, Subpart D, plus recursively resolved cross-references
- **Out of scope:** Human review UI, payment integration, multi-program graph, production infrastructure

## How It Works

### 1. Discovery & Ingestion
An agent starts at the known anchor sections of 44 CFR Part 206 and autonomously identifies which sections are relevant to rental assistance eligibility. It chases cross-references recursively until the dependency tree bottoms out. All fetched CFR text is cached to disk.

### 2. Translation
A translation agent reads each relevant CFR section and converts the regulatory prose into structured Fact Graph node definitions — typed facts, explicit dependencies, structured conditions, and CFR citations with paragraph-level provenance. Ambiguous or underspecified rules are flagged explicitly rather than resolved silently.

### 3. Validation
The assembled Fact Graph is validated against a schema: all dependency references must resolve, all terminal facts must be present, all citations must trace to fetched source text. A validation report surfaces any gaps.

### 4. Determination
Given an applicant's facts, the engine resolves eligibility incrementally, producing a determination with a full dependency trace. Every resolved fact cites the CFR provision that produced it. Missing inputs are surfaced cleanly rather than treated as errors.

### 5. Testing
A synthetic test suite of 20 applicant scenarios covers clearly eligible, clearly ineligible, edge cases, and incomplete information. The test runner reports pass/fail with resolution traces for any failure.

## Getting Started

```bash
# Install dependencies
pip install -e .

# Copy and fill in your API key
cp .env.example .env

# Run the full pipeline (discovery → translation → validate)
python -m cli run-pipeline

# Run all synthetic test cases
python -m cli test

# Run a determination for a specific applicant
python -m cli determine --input path/to/applicant.json

# View the fact graph as a dependency tree
python -m cli show-graph

# View the validation report
python -m cli show-validation
```

## Cost

The pipeline makes Anthropic API calls for CFR relevance scoring, translation, and synthetic test case generation. All outputs are cached to disk — re-running the pipeline makes zero API calls unless `--refresh` is passed. A full run from scratch should cost under $20. Cost is logged to `data/cost_log.json` and printed at the end of each pipeline run.

You will need an Anthropic API key from [console.anthropic.com](https://console.anthropic.com). This is separate from a claude.ai subscription.

## Key Design Decisions

**Ambiguity is a valid output.** If a CFR rule is genuinely underspecified, the system flags it rather than making a silent interpretive choice. Making ambiguity legible is a feature, not a limitation.

**Provenance is non-negotiable.** Every resolved fact traces to a CFR citation with paragraph. A determination without provenance is not a valid output.

**The schema is the contract.** Translation agent outputs that don't validate against the Fact Graph schema are pipeline failures, surfaced loudly.

**Partial information is first-class.** The engine never errors on missing inputs. It resolves what it can, surfaces what it's waiting for, and continues as new facts arrive.

## Background

This project draws on:
- [IRS Direct File](https://github.com/direct-file) — the Fact Graph architecture this system reimplements in Python
- [eCFR](https://www.ecfr.gov) — the public, machine-readable Code of Federal Regulations
- [FEMA Individual Assistance](https://www.fema.gov/assistance/individual) — 44 CFR Part 206, Subpart D

## Status

Pilot / proof of concept. Not for production use.