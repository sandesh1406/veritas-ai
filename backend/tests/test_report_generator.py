import pytest
import sys
import os

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from app.services.report_generator import ReportGenerator
from app.models.schemas import (
    ClaimExtracted, CitationExtracted, PublicationRetrieved,
    EvidenceExtracted, VerificationResult, VerificationVerdict
)


class TestReportGenerator:
    def setup_method(self):
        self.generator = ReportGenerator()

    def test_generate_report_basic(self):
        """Test basic PDF report generation."""
        claims = [ClaimExtracted(id="1", claim_text="Test claim", claim_type="general", page_number=1)]
        citations = [CitationExtracted(id="1", claim_id="1", citation_text="[1] Test citation", reference_number="1", doi="10.1234/test")]
        publications = [PublicationRetrieved(id="1", citation_id="1", title="Test Paper", authors="Smith", doi="10.1234/test", publication_year=2023, source_url="https://example.com", retrieval_status="completed")]
        evidence = [EvidenceExtracted(id="1", claim_id="1", publication_id="1", evidence_text="Test evidence", source_location="abstract")]
        verifications = [VerificationResult(id="1", claim_id="1", verdict=VerificationVerdict.SUPPORTED, confidence_score=85.0, explanation="Supported", evidence_status="Abstract available", model_version="claude-3-5-sonnet")]

        pdf_bytes = self.generator.generate_report("test.pdf", claims, citations, publications, evidence, verifications)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000  # Should be a valid PDF
        assert pdf_bytes[:4] == b'%PDF'  # PDF magic bytes

    def test_generate_report_all_verdicts(self):
        """Test report with all 6 verdict types."""
        claims = [
            ClaimExtracted(id=str(i), claim_text=f"Claim {i}", claim_type="general", page_number=1)
            for i in range(6)
        ]
        verifications = [
            VerificationResult(
                id=str(i), claim_id=str(i),
                verdict=v, confidence_score=80.0,
                explanation="Test", evidence_status="Test",
                model_version="claude-3-5-sonnet"
            )
            for i, v in enumerate([
                VerificationVerdict.SUPPORTED,
                VerificationVerdict.PARTIALLY_SUPPORTED,
                VerificationVerdict.UNSUPPORTED,
                VerificationVerdict.CONTRADICTORY,
                VerificationVerdict.POTENTIALLY_OUTDATED,
                VerificationVerdict.NEEDS_REVIEW,
            ])
        ]

        pdf_bytes = self.generator.generate_report("test.pdf", claims, [], [], [], verifications)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000

    def test_generate_report_no_claims(self):
        """Test report generation with no claims (empty document)."""
        pdf_bytes = self.generator.generate_report("empty.pdf", [], [], [], [], [])
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 500
        assert pdf_bytes[:4] == b'%PDF'