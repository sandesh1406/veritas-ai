import pytest
import sys
import os

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from datetime import datetime
from app.models.schemas import (
    VerificationVerdict,
    ProcessingStatus,
    DocumentStatusResponse,
    HealthResponse,
)


class TestVerificationVerdict:
    def test_all_verdicts_exist(self):
        """Verify all 6 verification verdicts are defined."""
        verdicts = list(VerificationVerdict)
        assert len(verdicts) == 6

    def test_verdict_values(self):
        """Verify exact verdict values match requirements."""
        assert VerificationVerdict.SUPPORTED == "SUPPORTED"
        assert VerificationVerdict.PARTIALLY_SUPPORTED == "PARTIALLY_SUPPORTED"
        assert VerificationVerdict.UNSUPPORTED == "UNSUPPORTED"
        assert VerificationVerdict.CONTRADICTORY == "CONTRADICTORY"
        assert VerificationVerdict.POTENTIALLY_OUTDATED == "POTENTIALLY_OUTDATED"
        assert VerificationVerdict.NEEDS_REVIEW == "NEEDS_REVIEW"


class TestProcessingStatus:
    def test_status_values(self):
        assert ProcessingStatus.QUEUED == "queued"
        assert ProcessingStatus.PROCESSING == "processing"
        assert ProcessingStatus.COMPLETED == "completed"
        assert ProcessingStatus.FAILED == "failed"


class TestDocumentStatusResponse:
    def test_document_status_response_creation(self):
        resp = DocumentStatusResponse(
            document_id="test-id",
            processing_status=ProcessingStatus.COMPLETED,
            claims_extracted=5,
            citations_found=10,
            publications_retrieved=8,
            verifications_completed=5,
            updated_at=datetime.now(),
        )
        assert resp.document_id == "test-id"
        assert resp.claims_extracted == 5


class TestHealthResponse:
    def test_health_response_defaults(self):
        resp = HealthResponse(status="healthy")
        assert resp.status == "healthy"
        assert resp.version == "1.0.0"