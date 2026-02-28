"""
Pipeline unit tests using mocked httpx and anthropic clients.

All tests run fully offline — no API calls, no network access.
Tests cover:
  - Cache hit/miss behavior
  - Discovery relevance response parsing
  - Cross-reference extraction
  - Translation schema validation
  - Translation error handling
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.fixtures.anthropic_responses import (
    RELEVANCE_RESPONSE_NOT_RELEVANT,
    RELEVANCE_RESPONSE_RELEVANT,
    TRANSLATION_RESPONSE,
    make_relevance_response,
)
from tests.fixtures.cfr_responses import (
    CFR_44_206_113,
    ECFR_STRUCTURE_PART_206,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(data: dict[str, Any], status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response from a dict."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = data
    response.raise_for_status = MagicMock()
    return response


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestCache:
    def test_cache_miss_returns_none(self, tmp_path: Path) -> None:
        with patch("pipeline.cache.DATA_DIR", tmp_path):
            with patch("pipeline.cache.CATEGORY_TO_DIR", {
                "cfr_cache": tmp_path / "cfr_cache",
                "fact_graph_defs": tmp_path / "fact_graph_defs",
                "test_cases": tmp_path / "test_cases",
            }):
                from pipeline.cache import read_cache
                result = read_cache("cfr_cache", "nonexistent_key")
                assert result is None

    def test_write_then_read(self, tmp_path: Path) -> None:
        cat_dir = tmp_path / "cfr_cache"
        cat_dir.mkdir(parents=True)
        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": cat_dir,
            "fact_graph_defs": tmp_path / "fact_graph_defs",
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.cache import read_cache, write_cache
            data = {"key": "value", "number": 42}
            write_cache("cfr_cache", "test_key", data)
            result = read_cache("cfr_cache", "test_key")
            assert result == data

    def test_force_bypass_returns_none(self, tmp_path: Path) -> None:
        cat_dir = tmp_path / "cfr_cache"
        cat_dir.mkdir(parents=True)
        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": cat_dir,
            "fact_graph_defs": tmp_path / "fact_graph_defs",
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.cache import read_cache, write_cache
            write_cache("cfr_cache", "test_key", {"cached": True})
            # force=True should bypass cache.
            result = read_cache("cfr_cache", "test_key", force=True)
            assert result is None

    def test_unknown_category_raises(self) -> None:
        from pipeline.cache import read_cache
        with pytest.raises(ValueError, match="Unknown cache category"):
            read_cache("nonexistent_category", "key")


# ---------------------------------------------------------------------------
# Discovery tests (mocked httpx + anthropic)
# ---------------------------------------------------------------------------

class TestDiscovery:
    def _make_agent(
        self, section_data: dict[str, Any], relevance_response: Any, tmp_path: Path
    ) -> Any:
        from pipeline.discovery import DiscoveryAgent

        # Mock httpx client.
        http_client = MagicMock(spec=httpx.Client)
        http_client.get.return_value = _make_httpx_response(section_data)

        # Mock anthropic client.
        llm_client = MagicMock()
        llm_client.messages.create.return_value = relevance_response

        return DiscoveryAgent(httpx_client=http_client, anthropic_client=llm_client)

    def test_fetch_section_caches_to_disk(self, tmp_path: Path) -> None:
        """Fetching a section should write it to the cfr_cache directory."""
        cat_dir = tmp_path / "cfr_cache"
        cat_dir.mkdir(parents=True)

        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": cat_dir,
            "fact_graph_defs": tmp_path / "fact_graph_defs",
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.discovery import DiscoveryAgent

            http_client = MagicMock(spec=httpx.Client)
            http_client.get.return_value = _make_httpx_response(CFR_44_206_113)
            agent = DiscoveryAgent(httpx_client=http_client)

            result = agent.fetch_section_text(44, "206.113")
            assert result["section"] == "206.113"
            # Should have been cached.
            cache_file = cat_dir / "title_44_section_206_113.json"
            assert cache_file.exists()

    def test_fetch_section_uses_cache_on_second_call(self, tmp_path: Path) -> None:
        """Second fetch of the same section should use disk cache, not HTTP."""
        cat_dir = tmp_path / "cfr_cache"
        cat_dir.mkdir(parents=True)

        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": cat_dir,
            "fact_graph_defs": tmp_path / "fact_graph_defs",
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.discovery import DiscoveryAgent

            http_client = MagicMock(spec=httpx.Client)
            http_client.get.return_value = _make_httpx_response(CFR_44_206_113)
            agent = DiscoveryAgent(httpx_client=http_client)

            agent.fetch_section_text(44, "206.113")
            agent.fetch_section_text(44, "206.113")  # Second call.
            # HTTP should only have been called once.
            assert http_client.get.call_count == 1

    def test_relevance_check_parses_response(self, tmp_path: Path) -> None:
        """check_relevance should parse the LLM JSON response correctly."""
        from pipeline.discovery import DiscoveryAgent

        llm_client = MagicMock()
        llm_client.messages.create.return_value = RELEVANCE_RESPONSE_RELEVANT
        agent = DiscoveryAgent(anthropic_client=llm_client)

        result = agent.check_relevance(44, "206.113", "section text here")
        assert result["relevant"] is True
        assert isinstance(result["cross_references"], list)
        assert len(result["cross_references"]) > 0

    def test_relevance_check_not_relevant(self, tmp_path: Path) -> None:
        from pipeline.discovery import DiscoveryAgent

        llm_client = MagicMock()
        llm_client.messages.create.return_value = RELEVANCE_RESPONSE_NOT_RELEVANT
        agent = DiscoveryAgent(anthropic_client=llm_client)

        result = agent.check_relevance(44, "206.112", "registration period text")
        assert result["relevant"] is False

    def test_cross_reference_extraction(self) -> None:
        """Cross-references from RELEVANCE_RESPONSE_RELEVANT should include '206.117'."""
        from pipeline.discovery import DiscoveryAgent

        llm_client = MagicMock()
        llm_client.messages.create.return_value = RELEVANCE_RESPONSE_RELEVANT
        agent = DiscoveryAgent(anthropic_client=llm_client)

        result = agent.check_relevance(44, "206.113", "text")
        cross_refs = result["cross_references"]
        assert any("206.117" in ref for ref in cross_refs), (
            f"Expected '206.117' in cross_references, got: {cross_refs}"
        )


# ---------------------------------------------------------------------------
# Translation tests (mocked anthropic)
# ---------------------------------------------------------------------------

class TestTranslation:
    def test_translate_section_returns_fact_nodes(self, tmp_path: Path) -> None:
        """translate_section should return a list of validated FactNodes."""
        defs_dir = tmp_path / "fact_graph_defs"
        defs_dir.mkdir(parents=True)

        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": tmp_path / "cfr_cache",
            "fact_graph_defs": defs_dir,
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.translation import TranslationAgent

            llm_client = MagicMock()
            llm_client.messages.create.return_value = TRANSLATION_RESPONSE
            agent = TranslationAgent(anthropic_client=llm_client)

            section_text = CFR_44_206_113["content"]
            nodes = agent.translate_section(
                title=44,
                section="206.113",
                section_text=section_text,
                existing_fact_ids=[],
            )
            assert len(nodes) >= 3, f"Expected ≥3 FactNodes, got {len(nodes)}"
            # All must be FactNode instances with valid IDs.
            for node in nodes:
                from fact_graph.schema import FactNode
                assert isinstance(node, FactNode)
                assert node.id != ""
                assert "_" in node.id  # snake_case

    def test_translate_section_caches_output(self, tmp_path: Path) -> None:
        """Translated nodes should be cached to disk."""
        defs_dir = tmp_path / "fact_graph_defs"
        defs_dir.mkdir(parents=True)

        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": tmp_path / "cfr_cache",
            "fact_graph_defs": defs_dir,
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.translation import TranslationAgent

            llm_client = MagicMock()
            llm_client.messages.create.return_value = TRANSLATION_RESPONSE
            agent = TranslationAgent(anthropic_client=llm_client)

            agent.translate_section(44, "206.113", CFR_44_206_113["content"], [])
            cache_file = defs_dir / "title_44_section_206_113.json"
            assert cache_file.exists()

    def test_translate_section_uses_cache_on_second_call(self, tmp_path: Path) -> None:
        """Second translation of the same section should use disk cache."""
        defs_dir = tmp_path / "fact_graph_defs"
        defs_dir.mkdir(parents=True)

        with patch("pipeline.cache.CATEGORY_TO_DIR", {
            "cfr_cache": tmp_path / "cfr_cache",
            "fact_graph_defs": defs_dir,
            "test_cases": tmp_path / "test_cases",
        }):
            from pipeline.translation import TranslationAgent

            llm_client = MagicMock()
            llm_client.messages.create.return_value = TRANSLATION_RESPONSE
            agent = TranslationAgent(anthropic_client=llm_client)

            agent.translate_section(44, "206.113", CFR_44_206_113["content"], [])
            agent.translate_section(44, "206.113", CFR_44_206_113["content"], [])
            assert llm_client.messages.create.call_count == 1

    def test_validate_graph_catches_broken_deps(self) -> None:
        """validate_graph should flag broken dependency references."""
        from fact_graph.schema import FactGraph, FactNode, FactType
        from pipeline.translation import TranslationAgent

        bad_node = FactNode(
            id="leaf_a",
            label="Leaf A",
            fact_type=FactType.BOOLEAN,
            dependencies=["nonexistent_fact"],
        )
        graph = FactGraph(
            nodes={"leaf_a": bad_node},
            terminal_fact_ids=[],
        )
        agent = TranslationAgent()
        with patch("pipeline.translation.write_cache"):
            report = agent.validate_graph(graph)
        assert not report.valid
        assert len(report.broken_dependency_refs) > 0

    def test_validate_graph_catches_missing_terminal_facts(self) -> None:
        """validate_graph should flag missing required terminal facts."""
        from fact_graph.schema import FactGraph, FactNode, FactType
        from pipeline.translation import TranslationAgent

        node = FactNode(
            id="some_fact",
            label="Some Fact",
            fact_type=FactType.BOOLEAN,
        )
        graph = FactGraph(nodes={"some_fact": node}, terminal_fact_ids=[])
        agent = TranslationAgent()
        with patch("pipeline.translation.write_cache"):
            report = agent.validate_graph(graph)
        assert not report.terminal_facts_present
        assert "applicant_eligible_for_rental_assistance" in report.missing_terminal_facts

    def test_validate_graph_valid(self) -> None:
        """validate_graph should pass for the hardcoded FEMA IA fixture."""
        from pipeline.translation import TranslationAgent
        from tests.fixtures.fema_ia_graph import build_fema_ia_graph

        graph = build_fema_ia_graph()
        agent = TranslationAgent()
        with patch("pipeline.translation.write_cache"):
            report = agent.validate_graph(graph)
        assert report.terminal_facts_present
        assert report.missing_terminal_facts == []
        assert report.broken_dependency_refs == []
