import pytest
import sys
import os

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from app.services.research_retrieval import (
    CrossrefClient, OpenAlexClient, SemanticScholarClient,
    ResearchRetrievalService, PublicationMetadata
)


class TestCrossrefClient:
    def setup_method(self):
        self.client = CrossrefClient()

    def test_parse_work(self):
        data = {
            "title": ["Test Paper Title"],
            "author": [{"given": "John", "family": "Smith"}, {"given": "Jane", "family": "Doe"}],
            "DOI": "10.1234/test",
            "published-print": {"date-parts": [[2023]]},
            "URL": "https://example.com/paper"
        }
        result = self.client._parse_work(data)
        assert result is not None
        assert result.title == "Test Paper Title"
        assert "John Smith" in result.authors
        assert result.doi == "10.1234/test"
        assert result.publication_year == 2023
        assert result.source == "crossref"

    def test_parse_work_no_title(self):
        """Test parsing work with no title returns None."""
        data = {"author": [{"given": "John", "family": "Smith"}]}
        result = self.client._parse_work(data)
        assert result is None

    def test_close(self):
        """Test client close method."""
        # Should not raise
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.client.close())


class TestOpenAlexClient:
    def setup_method(self):
        self.client = OpenAlexClient()

    def test_parse_work(self):
        data = {
            "display_name": "Test Paper",
            "authorships": [{"author": {"display_name": "John Smith"}}, {"author": {"display_name": "Jane Doe"}}],
            "doi": "https://doi.org/10.1234/test",
            "publication_year": 2023,
            "id": "https://openalex.org/W123",
            "locations": [{"is_oa": True, "pdf_url": "https://example.com/paper.pdf"}]
        }
        result = self.client._parse_work(data)
        assert result is not None
        assert result.title == "Test Paper"
        assert "John Smith" in result.authors
        assert result.doi == "10.1234/test"
        assert result.publication_year == 2023
        assert result.full_text_url == "https://example.com/paper.pdf"
        assert result.source == "openalex"

    def test_close(self):
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.client.close())


class TestSemanticScholarClient:
    def setup_method(self):
        self.client = SemanticScholarClient()

    def test_parse_paper(self):
        data = {
            "title": "Test Paper",
            "authors": [{"name": "John Smith"}, {"name": "Jane Doe"}],
            "doi": "10.1234/test",
            "year": 2023,
            "url": "https://semanticscholar.org/paper/123",
            "abstract": "This is an abstract.",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"}
        }
        result = self.client._parse_paper(data)
        assert result is not None
        assert result.title == "Test Paper"
        assert "John Smith" in result.authors
        assert result.doi == "10.1234/test"
        assert result.publication_year == 2023
        assert result.abstract == "This is an abstract."
        assert result.full_text_url == "https://example.com/paper.pdf"
        assert result.source == "semantic_scholar"

    def test_close(self):
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.client.close())


class TestResearchRetrievalService:
    def setup_method(self):
        self.service = ResearchRetrievalService()

    def test_extract_title_from_citation_standard(self):
        """Test extracting title from standard citation format."""
        citation = "[1] Smith J, Doe J. A great paper about methods. Nature, 2023. DOI 10.1234/test"
        title = self.service._extract_title_from_citation(citation)
        assert "great paper about methods" in title.lower()

    def test_extract_title_from_citation_with_in(self):
        """Test extracting title with 'In:' pattern."""
        citation = "[1] Smith J. Title here. In: Proceedings of Conference, 2023."
        title = self.service._extract_title_from_citation(citation)
        assert "title here" in title.lower()

    def test_titles_match_exact(self):
        """Test exact title matching."""
        assert self.service._titles_match("A Great Paper About Methods", "A Great Paper About Methods") == True

    def test_titles_match_fuzzy(self):
        """Test fuzzy title matching."""
        assert self.service._titles_match("A Great Paper About Methods", "A Great Paper on Methods") == True

    def test_titles_mismatch(self):
        """Test title mismatch."""
        assert self.service._titles_match("Completely Different", "Something Else") == False