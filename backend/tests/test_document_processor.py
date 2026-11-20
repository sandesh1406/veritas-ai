import pytest
import sys
import os

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from app.services.document_processor import DocumentProcessor, TextChunk, ExtractedClaim, ExtractedCitation


class TestDocumentProcessor:
    def setup_method(self):
        self.processor = DocumentProcessor(max_claims=10)

    def test_text_chunk_dataclass(self):
        chunk = TextChunk(text="Hello world", page_number=1)
        assert chunk.text == "Hello world"
        assert chunk.page_number == 1

    def test_find_bibliography_start(self):
        chunks = [
            TextChunk("Introduction text here.", 1),
            TextChunk("Methods and results text.", 2),
            TextChunk("References\n[1] Smith et al. Nature 2020.", 3),
        ]
        idx = self.processor.find_bibliography_start(chunks)
        assert idx == 2

    def test_find_bibliography_start_not_found(self):
        chunks = [
            TextChunk("Just content.", 1),
        ]
        idx = self.processor.find_bibliography_start(chunks)
        assert idx is None

    def test_find_bibliography_start_various_patterns(self):
        # Test various bibliography section markers
        for marker in ["References", "Bibliography", "Works Cited", "Literature Cited", "Reference List"]:
            chunks = [TextChunk(f"Some text\n{marker}\n[1] Test.", 1)]
            idx = self.processor.find_bibliography_start(chunks)
            assert idx is not None, f"Failed to find: {marker}"

    def test_classify_claim(self):
        assert self.processor._classify_claim("We propose a new method") == "methodological"
        assert self.processor._classify_claim("Significant correlation found") == "correlational"
        assert self.processor._classify_claim("Causal effect was observed") == "causal"
        assert self.processor._classify_claim("P < 0.05 significant") == "statistical"
        assert self.processor._classify_claim("General statement") == "general"

    def test_classify_claim_proposed(self):
        assert self.processor._classify_claim("We propose a new framework") == "methodological"
        assert self.processor._classify_claim("This paper introduces a method") == "methodological"
        assert self.processor._classify_claim("We develop a novel approach") == "methodological"

    def test_classify_claim_correlation(self):
        assert self.processor._classify_claim("There is a correlation between variables") == "correlational"
        assert self.processor._classify_claim("The association was found") == "correlational"

    def test_classify_claim_causal(self):
        assert self.processor._classify_claim("This causes the result") == "causal"
        assert self.processor._classify_claim("The impact on health") == "causal"

    def test_extract_claims_simple(self):
        chunks = [
            TextChunk("We demonstrate that our method significantly improves accuracy. This study shows novel results.", 1),
            TextChunk("References\n[1] Test.", 2),
        ]
        claims = self.processor.extract_claims(chunks)
        assert len(claims) >= 1
        assert "improves accuracy" in claims[0].claim_text

    def test_extract_claims_statistical(self):
        chunks = [
            TextChunk("The results were statistically significant (p < 0.05). Our data shows clear patterns.", 1),
            TextChunk("References\n[1] Test.", 2),
        ]
        claims = self.processor.extract_claims(chunks)
        assert len(claims) >= 1
        assert "statistically significant" in claims[0].claim_text.lower()

    def test_extract_claims_methodological(self):
        chunks = [
            TextChunk("We propose a new method for analysis. Our framework enables faster processing.", 1),
            TextChunk("References\n[1] Test.", 2),
        ]
        claims = self.processor.extract_claims(chunks)
        assert len(claims) >= 1
        assert "method" in claims[0].claim_text.lower() or "propose" in claims[0].claim_text.lower()

    def test_extract_citations(self):
        chunks = [
            TextChunk("Main text.", 1),
            TextChunk("References\n[1] Smith J. Title. Journal, 2020. DOI 10.1234/test\n[2] Jones K. Another. Conf, 2019.", 2),
        ]
        citations = self.processor.extract_citations(chunks)
        assert len(citations) >= 1
        assert citations[0].reference_number == "1"
        assert citations[0].doi == "10.1234/test"

    def test_extract_citations_numbered(self):
        chunks = [
            TextChunk("References\n1. Author A. Paper Title. Journal, 2020. DOI 10.1234/test\n2. Author B. Another Paper. Conf, 2019.", 1),
        ]
        citations = self.processor.extract_citations(chunks)
        assert len(citations) >= 1
        assert citations[0].reference_number == "1"

    def test_extract_citations_no_doi(self):
        chunks = [
            TextChunk("References\n[1] Smith J. Title. Journal, 2020.\n[2] Jones K. Another Paper. Conf, 2019.", 1),
        ]
        citations = self.processor.extract_citations(chunks)
        assert len(citations) >= 1
        # DOI may or may not be extracted depending on format

    def test_map_claims_to_citations(self):
        claims = [
            ExtractedClaim(claim_text="Method improves accuracy", claim_type="general", page_number=1)
        ]
        citations = [
            ExtractedCitation(citation_text="Test citation", reference_number="1", doi="10.1234/test", claim_text="")
        ]
        chunks = [
            TextChunk("Method improves accuracy [1].", 1),
        ]
        mapped = self.processor.map_claims_to_citations(claims, citations.copy(), chunks)
        assert len(mapped) == 1
        # The citation should be mapped to the claim
        assert mapped[0].claim_text == "Method improves accuracy"

    def test_extract_text_pdf(self):
        # Test PDF text extraction with simple content
        # This tests the method exists, actual PDF would need real bytes
        assert hasattr(self.processor, 'extract_text')

    def test_extract_text_docx(self):
        # Test DOCX text extraction method exists
        assert hasattr(self.processor, 'extract_text')