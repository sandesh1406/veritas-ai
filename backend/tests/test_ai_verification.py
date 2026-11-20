"""Tests for AI Verification Service (integration tests)."""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'
os.environ['AI_PROVIDER'] = 'gemini'

from app.services.ai_verification import AIVerificationService
from app.services.ai_provider import ClaimWithEvidence, VerificationOutput
from app.models.schemas import VerificationVerdict


class TestAIVerificationService:
    def setup_method(self):
        with patch('app.services.ai_verification.get_ai_provider') as mock_get_provider:
            self.mock_provider = AsyncMock()
            mock_get_provider.return_value = self.mock_provider

            self.service = AIVerificationService()

    @pytest.mark.asyncio
    async def test_verify_claim_supported(self):
        """Test verification returns SUPPORTED verdict."""
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.SUPPORTED,
            confidence_score=85,
            explanation="Evidence directly supports the claim",
            evidence_status="Full abstract available"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-1",
            claim_text="Our method improves accuracy",
            citation_text="[1] Smith et al. Method improves accuracy. Nature 2023.",
            evidence_passages=["The proposed method improves accuracy by 15% on benchmarks."],
            publication_title="Test Paper"
        )

        result = await self.service.verify_claim(claim)

        assert result.verdict == VerificationVerdict.SUPPORTED
        assert result.confidence_score == 85
        assert "supports" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_verify_claim_needs_review_no_evidence(self):
        """Test NEEDS_REVIEW when no evidence passages."""
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.NEEDS_REVIEW,
            confidence_score=0,
            explanation="No evidence retrieved",
            evidence_status="No accessible full text"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-2",
            claim_text="Some claim",
            citation_text="[1] Unknown.",
            evidence_passages=[],
            publication_title="Unknown"
        )

        result = await self.service.verify_claim(claim)

        assert result.verdict == VerificationVerdict.NEEDS_REVIEW
        assert result.confidence_score == 0

    @pytest.mark.asyncio
    async def test_verify_claim_partially_supported(self):
        """Test PARTIALLY_SUPPORTED verdict."""
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.PARTIALLY_SUPPORTED,
            confidence_score=60,
            explanation="Partial support from multiple sources",
            evidence_status="Multiple abstract sources"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-3",
            claim_text="Method improves accuracy and speed",
            citation_text="[1] Mixed evidence.",
            evidence_passages=["Evidence for accuracy.", "Limited evidence for speed."],
            publication_title="Mixed Results Paper"
        )

        result = await self.service.verify_claim(claim)

        assert result.verdict == VerificationVerdict.PARTIALLY_SUPPORTED

    @pytest.mark.asyncio
    async def test_verify_claim_contradictory(self):
        """Test CONTRADICTORY verdict."""
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.CONTRADICTORY,
            confidence_score=95,
            explanation="Evidence directly contradicts the claim",
            evidence_status="Contradictory abstract"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-4",
            claim_text="Treatment reduces symptoms",
            citation_text="[1] Contradictory study.",
            evidence_passages=["Study shows symptoms increased with treatment."],
            publication_title="Contradictory Study"
        )

        result = await self.service.verify_claim(claim)

        assert result.verdict == VerificationVerdict.CONTRADICTORY

    @pytest.mark.asyncio
    async def test_verify_claim_error_fallback(self):
        """Test fallback to NEEDS_REVIEW on provider error."""
        # The provider handles errors internally and returns NEEDS_REVIEW
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.NEEDS_REVIEW,
            confidence_score=0,
            explanation="Verification failed due to error: API Error",
            evidence_status="Error during AI processing"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-5",
            claim_text="Test claim",
            citation_text="[1] Test.",
            evidence_passages=["Some evidence"],
            publication_title="Test Paper"
        )

        result = await self.service.verify_claim(claim)

        assert result.verdict == VerificationVerdict.NEEDS_REVIEW
        assert result.confidence_score == 0
        assert "error" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_verify_batch(self):
        """Test batch verification."""
        mock_outputs = [
            VerificationOutput(
                verdict=VerificationVerdict.SUPPORTED,
                confidence_score=80,
                explanation="Test",
                evidence_status="Test"
            ),
            VerificationOutput(
                verdict=VerificationVerdict.SUPPORTED,
                confidence_score=80,
                explanation="Test",
                evidence_status="Test"
            ),
        ]
        self.mock_provider.verify_batch = AsyncMock(return_value=mock_outputs)

        claims = [
            ClaimWithEvidence(claim_id="1", claim_text="Claim 1", citation_text="[1]", evidence_passages=["Evidence 1"], publication_title="Paper 1"),
            ClaimWithEvidence(claim_id="2", claim_text="Claim 2", citation_text="[2]", evidence_passages=["Evidence 2"], publication_title="Paper 2"),
        ]

        results = await self.service.verify_batch(claims)

        assert len(results) == 2
        assert all(r.verdict == VerificationVerdict.SUPPORTED for r in results)

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the service closes the provider."""
        await self.service.close()
        self.mock_provider.close.assert_called_once()