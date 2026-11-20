import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from app.services.evidence_extractor import EvidenceExtractor, EvidencePassage
from app.services.research_retrieval import ResearchRetrievalService, PublicationMetadata


class TestEvidenceExtractor:
    def setup_method(self):
        self.mock_research = MagicMock(spec=ResearchRetrievalService)
        self.extractor = EvidenceExtractor(self.mock_research)

    def test_extract_evidence_from_abstract(self):
        """Test extracting evidence from abstract."""
        claim = "Our method improves accuracy"
        publications = [
            PublicationMetadata(
                title="Test Paper",
                authors="Smith et al.",
                doi="10.1234/test",
                publication_year=2023,
                source_url="https://example.com",
                abstract="Our proposed method improves accuracy by 15% on standard benchmarks. The approach shows robust performance.",
                full_text_url=None,
            )
        ]

        import asyncio
        passages = asyncio.get_event_loop().run_until_complete(
            self.extractor.extract_evidence_for_claim(claim, publications)
        )

        assert len(passages) >= 1
        assert passages[0].source_location == "abstract"
        assert "improves accuracy" in passages[0].text.lower()

    def test_find_relevant_sentences(self):
        """Test keyword-based sentence relevance matching."""
        claim = "Our method improves accuracy on benchmark datasets"
        source = "The proposed method improves accuracy by 15% on standard benchmarks. Other methods show no improvement. Results are statistically significant with p < 0.05."

        relevant = self.extractor._find_relevant_sentences(claim, source, max_sentences=2)
        assert len(relevant) <= 2
        assert any("improves accuracy" in s.lower() for s in relevant)

    def test_find_relevant_sentences_no_overlap(self):
        """Test that irrelevant text returns empty list."""
        claim = "Method improves accuracy"
        source = "The weather is nice today. Cats are cute animals."
        relevant = self.extractor._find_relevant_sentences(claim, source, max_sentences=2)
        assert len(relevant) == 0

    def test_extract_evidence_no_publications(self):
        """Test with no publications returns empty list."""
        import asyncio
        passages = asyncio.get_event_loop().run_until_complete(
            self.extractor.extract_evidence_for_claim("claim", [])
        )
        assert passages == []

    def test_evidence_passage_dataclass(self):
        """Test EvidencePassage dataclass attributes."""
        passage = EvidencePassage(
            text="Evidence text",
            source_location="abstract",
            publication_id="pub-1"
        )
        assert passage.text == "Evidence text"
        assert passage.source_location == "abstract"
        assert passage.publication_id == "pub-1"