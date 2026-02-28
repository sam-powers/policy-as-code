"""
CFR Discovery & Ingestion Agent.

Fetches relevant CFR sections for FEMA IA rental assistance using a
citation-chasing strategy seeded from anchor sections in 44 CFR Part 206.
All fetched text is cached to disk before any LLM calls.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from html.parser import HTMLParser
from typing import Any

import anthropic
import httpx
from dotenv import load_dotenv

from .cache import read_cache, write_cache

load_dotenv()

# Anchor sections to start discovery from.
ANCHOR_SECTIONS: list[tuple[int, str]] = [
    (44, "206.110"),
    (44, "206.111"),
    (44, "206.112"),
    (44, "206.113"),
    (44, "206.114"),
    (44, "206.115"),
    (44, "206.117"),
    (44, "206.119"),
    (44, "59.1"),
]

# External (non-CFR) references — flagged but not chased.
EXTERNAL_REF_PATTERNS: list[str] = [
    r"\d+\s+U\.S\.C\.",
    r"HUD",
    r"Fair Market Rent",
]

ECFR_BASE = "https://api.ecfr.gov/api/versioner/v1"
MAX_DEPTH = int(os.getenv("MAX_DISCOVERY_DEPTH", "4"))
ECFR_DATE = os.getenv("ECFR_DATE", date.today().isoformat())

# Pricing for claude-sonnet-4-20250514
INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00

RELEVANCE_PROMPT = """\
You are a federal benefits policy analyst.

Read the CFR section text below and answer:
1. Is this section relevant to eligibility conditions, definitions, or benefit
   calculations for FEMA Individual Assistance rental assistance for flood-displaced
   applicants? (relevant: true/false)
2. Briefly explain why (reason: str, 1-2 sentences).
3. List all cross-references to other CFR sections mentioned (cross_references:
   list of strings like "206.117" or "44 CFR 59.1").

Return ONLY valid JSON with keys: relevant (bool), reason (str), cross_references (list[str]).
No preamble, no explanation outside the JSON.

CFR SECTION TEXT:
{section_text}
"""


class _HTMLStripper(HTMLParser):
    """Strip HTML tags from eCFR content field."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(text: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(text)
    return stripper.get_text()


def _normalize_section_ref(ref: str) -> str:
    """Normalize a cross-reference string to a bare section number, e.g. '206.117'."""
    ref = ref.strip()
    ref = re.sub(r"^(44\s+CFR\s+|§+\s*)", "", ref)
    return ref.strip()


def _is_external_ref(ref: str) -> bool:
    return any(re.search(p, ref, re.IGNORECASE) for p in EXTERNAL_REF_PATTERNS)


class DiscoveryAgent:
    """
    Autonomously discovers and fetches relevant CFR sections.

    Args:
        httpx_client: Injected httpx.Client for testing (None = real client).
        anthropic_client: Injected anthropic.Anthropic for testing (None = real client).
    """

    def __init__(
        self,
        httpx_client: httpx.Client | None = None,
        anthropic_client: anthropic.Anthropic | None = None,
    ) -> None:
        self._http = httpx_client or httpx.Client(timeout=30.0)
        self._llm = anthropic_client
        self._cost_entries: list[dict[str, Any]] = []

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

    def fetch_section_text(self, title: int, section: str, force: bool = False) -> dict[str, Any]:
        """Fetch a CFR section, using disk cache when available."""
        cache_key = f"title_{title}_section_{section.replace('.', '_')}"
        cached = read_cache("cfr_cache", cache_key, force=force)
        if cached is not None:
            return cached

        url = f"{ECFR_BASE}/full/{ECFR_DATE}/title-{title}.json"
        resp = self._http.get(url, params={"section": section})
        resp.raise_for_status()
        raw = resp.json()

        content = raw.get("content", "")
        if "<" in content:
            content = _strip_html(content)

        result: dict[str, Any] = {
            "title": title,
            "section": section,
            "last_fetched": ECFR_DATE,
            "content": content,
            "raw_meta": raw.get("meta", {}),
        }
        write_cache("cfr_cache", cache_key, result)
        return result

    def check_relevance(
        self, title: int, section: str, section_text: str
    ) -> dict[str, Any]:
        """Call the LLM to assess whether a section is relevant and extract cross-refs."""
        llm = self._get_llm()
        prompt = RELEVANCE_PROMPT.format(section_text=section_text[:8000])
        response = llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        self._log_cost(f"{title}_CFR_{section}_relevance", response.usage)
        first_block = response.content[0] if response.content else None
        text = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else "{}"
        try:
            result: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            result = {"relevant": False, "reason": "Parse error", "cross_references": []}
        return result

    def run(self, force: bool = False) -> dict[str, Any]:
        """
        Run the full discovery pipeline.

        Returns the manifest dict (also written to cfr_cache/manifest.json).
        """
        visited: set[str] = set()
        queue: list[tuple[int, str, int]] = [
            (title, section, 0) for title, section in ANCHOR_SECTIONS
        ]
        manifest_entries: list[dict[str, Any]] = []
        external_refs: list[dict[str, Any]] = []

        while queue:
            title, section, depth = queue.pop(0)
            key = f"{title}_{section}"
            if key in visited:
                continue
            visited.add(key)

            # Fetch and cache section text.
            try:
                section_data = self.fetch_section_text(title, section, force=force)
            except Exception as e:
                manifest_entries.append(
                    {
                        "title": title,
                        "section": section,
                        "relevant": False,
                        "reason": f"Fetch error: {e}",
                        "cross_references": [],
                        "depth": depth,
                    }
                )
                continue

            section_text = section_data.get("content", "")

            # LLM relevance pass.
            try:
                relevance = self.check_relevance(title, section, section_text)
            except RuntimeError:
                # No API key — mark as relevant by default (anchor sections are known relevant).
                relevance = {
                    "relevant": depth == 0,
                    "reason": "API key not configured; assumed relevant at depth 0.",
                    "cross_references": [],
                }

            is_relevant = relevance.get("relevant", False)
            cross_refs: list[str] = relevance.get("cross_references", [])

            entry: dict[str, Any] = {
                "title": title,
                "section": section,
                "relevant": is_relevant,
                "reason": relevance.get("reason", ""),
                "cross_references": cross_refs,
                "depth": depth,
                "cache_key": f"title_{title}_section_{section.replace('.', '_')}",
                "last_fetched": ECFR_DATE,
            }
            manifest_entries.append(entry)

            # Chase cross-references if relevant and within depth limit.
            if is_relevant and depth < MAX_DEPTH:
                for ref in cross_refs:
                    if _is_external_ref(ref):
                        external_refs.append(
                            {
                                "citation": ref,
                                "description": "External/statutory reference",
                                "reference_type": "statutory",
                            }
                        )
                        continue
                    normalized = _normalize_section_ref(ref)
                    # Assume same title (44) unless the ref includes a different title.
                    ref_title = title
                    ref_key = f"{ref_title}_{normalized}"
                    if ref_key not in visited:
                        queue.append((ref_title, normalized, depth + 1))

            time.sleep(0.2)  # Polite rate-limiting.

        manifest: dict[str, Any] = {
            "fetched_sections": manifest_entries,
            "external_references": external_refs,
            "fetch_date": ECFR_DATE,
        }
        write_cache("cfr_cache", "manifest", manifest)
        return manifest

    def _log_cost(self, label: str, usage: Any) -> None:
        from pathlib import Path
        import json as _json
        cost_path = Path(__file__).parent.parent / "data" / "cost_log.json"
        entry = {
            "timestamp": ECFR_DATE,
            "section": label,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": (
                usage.input_tokens / 1_000_000 * INPUT_COST_PER_M
                + usage.output_tokens / 1_000_000 * OUTPUT_COST_PER_M
            ),
        }
        existing: list[dict[str, Any]] = []
        if cost_path.exists():
            try:
                existing = _json.loads(cost_path.read_text())
            except Exception:
                pass
        existing.append(entry)
        cost_path.write_text(_json.dumps(existing, indent=2))
