"""Tests for AI provider abstraction and implementations."""

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

from app.services.ai_provider import (
    AIProvider,
    ClaimWithEvidence,
    VerificationOutput,
    VerificationVerdict,
    get_ai_provider,
)
from app.models.schemas import VerificationVerdict as SchemaVerificationVerdict


class TestAIProviderBase:
    """Test the AIProvider base class functionality."""

    def setup_method(self):
        """Set up a mock provider for testing."""
        class MockProvider(AIProvider):
            def _get_model_name(self):
                return "test-model"

            async def _call_model(self, prompt: str, system_prompt: str) -> str:
                return '{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Test", "evidence_status": "Test"}'

            async def close(self):
                pass

        self.provider = MockProvider()

    def test_format_evidence_with_passages(self):
        """Test evidence formatting with passages."""
        passages = ["Passage 1", "Passage 2", "Passage 3"]
        result = self.provider._format_evidence(passages)
        assert "[Passage 1]: Passage 1" in result
        assert "[Passage 2]: Passage 2" in result
        assert "[Passage 3]: Passage 3" in result

    def test_format_evidence_empty(self):
        """Test evidence formatting with no passages."""
        result = self.provider._format_evidence([])
        assert "NO EVIDENCE RETRIEVED" in result

    def test_format_evidence_truncates(self):
        """Test evidence formatting truncates long passages."""
        long_passage = "x" * 3000
        result = self.provider._format_evidence([long_passage])
        assert len(result) < 2500  # Should be truncated to ~2000 chars

    def test_format_evidence_limits_to_5(self):
        """Test evidence formatting limits to 5 passages."""
        passages = [f"Passage {i}" for i in range(10)]
        result = self.provider._format_evidence(passages)
        # Should only have 5 passages
        assert result.count("[Passage") == 5

    def test_build_prompt(self):
        """Test prompt building from claim data."""
        claim = ClaimWithEvidence(
            claim_id="test-1",
            claim_text="Test claim",
            citation_text="[1] Test citation",
            evidence_passages=["Evidence 1"],
            publication_title="Test Paper"
        )
        prompt = self.provider._build_prompt(claim)
        assert "Test claim" in prompt
        assert "Test citation" in prompt
        assert "Test Paper" in prompt
        assert "Evidence 1" in prompt

    def test_parse_response_json(self):
        """Test parsing valid JSON response."""
        content = '{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Test", "evidence_status": "Test"}'
        result = self.provider._parse_response(content)
        assert result.verdict == VerificationVerdict.SUPPORTED
        assert result.confidence_score == 85

    def test_parse_response_markdown_json(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        content = '```json\n{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Test", "evidence_status": "Test"}\n```'
        result = self.provider._parse_response(content)
        assert result.verdict == VerificationVerdict.SUPPORTED

    def test_parse_response_markdown_generic(self):
        """Test parsing JSON wrapped in generic markdown code blocks."""
        content = '```\n{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Test", "evidence_status": "Test"}\n```'
        result = self.provider._parse_response(content)
        assert result.verdict == VerificationVerdict.SUPPORTED


class TestGeminiProvider:
    """Test the Gemini provider implementation."""

    def setup_method(self):
        with patch('app.services.gemini_provider.genai.Client') as mock_client_class:
            self.mock_client = MagicMock()
            mock_client_class.return_value = self.mock_client

            from app.services.gemini_provider import GeminiProvider
            self.provider = GeminiProvider()

    @pytest.mark.asyncio
    async def test_verify_claim_supported(self):
        """Test successful verification with SUPPORTED verdict."""
        # Mock the generate_content response
        mock_response = MagicMock()
        mock_response.text = '{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Evidence supports claim", "evidence_status": "Full abstract available"}'
        self.mock_client.models.generate_content.return_value = mock_response

        claim = ClaimWithEvidence(
            claim_id="test-1",
            claim_text="Our method improves accuracy",
            citation_text="[1] Smith et al. Method improves accuracy. Nature 2023.",
            evidence_passages=["The proposed method improves accuracy by 15% on benchmarks."],
            publication_title="Test Paper"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.SUPPORTED
        assert result.confidence_score == 85

    @pytest.mark.asyncio
    async def test_verify_claim_needs_review_no_evidence(self):
        """Test NEEDS_REVIEW when no evidence passages."""
        mock_response = MagicMock()
        mock_response.text = '{"verdict": "NEEDS_REVIEW", "confidence_score": 0, "explanation": "No evidence retrieved", "evidence_status": "No accessible full text"}'
        self.mock_client.models.generate_content.return_value = mock_response

        claim = ClaimWithEvidence(
            claim_id="test-2",
            claim_text="Some claim",
            citation_text="[1] Unknown.",
            evidence_passages=[],
            publication_title="Unknown"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.NEEDS_REVIEW
        assert result.confidence_score == 0

    @pytest.mark.asyncio
    async def test_verify_claim_retry_on_rate_limit(self):
        """Test retry logic on rate limit error."""
        # First call fails with rate limit, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.text = None
        mock_response_fail.candidates = []

        mock_response_success = MagicMock()
        mock_response_success.text = '{"verdict": "SUPPORTED", "confidence_score": 80, "explanation": "Test", "evidence_status": "Test"}'

        self.mock_client.models.generate_content.side_effect = [
            Exception("Rate limit exceeded: 429"),
            mock_response_success
        ]

        claim = ClaimWithEvidence(
            claim_id="test-3",
            claim_text="Test claim",
            citation_text="[1] Test.",
            evidence_passages=["Evidence"],
            publication_title="Test"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.SUPPORTED
        assert self.mock_client.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_verify_claim_fallback_on_max_retries(self):
        """Test fallback to NEEDS_REVIEW after max retries."""
        self.mock_client.models.generate_content.side_effect = Exception("Rate limit exceeded: 429")

        claim = ClaimWithEvidence(
            claim_id="test-4",
            claim_text="Test claim",
            citation_text="[1] Test.",
            evidence_passages=["Evidence"],
            publication_title="Test"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.NEEDS_REVIEW
        assert result.confidence_score == 0
        assert "error" in result.explanation.lower()

    def test_model_name_from_settings(self):
        """Test that model name comes from settings."""
        assert self.provider.model_name == "gemini-1.5-flash"


class TestAnthropicProvider:
    """Test the Anthropic provider implementation."""

    def setup_method(self):
        with patch('app.services.anthropic_provider.AsyncAnthropic') as mock_client_class:
            self.mock_client = AsyncMock()
            mock_client_class.return_value = self.mock_client

            from app.services.anthropic_provider import AnthropicProvider
            self.provider = AnthropicProvider()

    @pytest.mark.asyncio
    async def test_verify_claim_supported(self):
        """Test successful verification with SUPPORTED verdict."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text='{"verdict": "SUPPORTED", "confidence_score": 85, "explanation": "Evidence supports claim", "evidence_status": "Full abstract available"}')]
        self.mock_client.messages.create = AsyncMock(return_value=mock_response)

        claim = ClaimWithEvidence(
            claim_id="test-1",
            claim_text="Our method improves accuracy",
            citation_text="[1] Smith et al. Method improves accuracy. Nature 2023.",
            evidence_passages=["The proposed method improves accuracy by 15% on benchmarks."],
            publication_title="Test Paper"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.SUPPORTED
        assert result.confidence_score == 85

    @pytest.mark.asyncio
    async def test_verify_claim_retry_on_rate_limit(self):
        """Test retry logic on rate limit error."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text='{"verdict": "SUPPORTED", "confidence_score": 80, "explanation": "Test", "evidence_status": "Test"}')]

        self.mock_client.messages.create = AsyncMock(side_effect=[
            Exception("Rate limit exceeded: 429"),
            mock_response
        ])

        claim = ClaimWithEvidence(
            claim_id="test-3",
            claim_text="Test claim",
            citation_text="[1] Test.",
            evidence_passages=["Evidence"],
            publication_title="Test"
        )

        result = await self.provider.verify_claim(claim)

        assert result.verdict == VerificationVerdict.SUPPORTED
        assert self.mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the client."""
        await self.provider.close()
        self.mock_client.close.assert_called_once()


class TestAIProviderFactory:
    """Test the AI provider factory function."""

    def test_get_gemini_provider(self):
        """Test factory returns Gemini provider when configured."""
        with patch.dict(os.environ, {'AI_PROVIDER': 'gemini'}):
            # Need to reload settings
            import importlib
            import app.core.config
            importlib.reload(app.core.config)

            with patch('app.services.ai_provider.GeminiProvider') as mock_gemini:
                mock_instance = MagicMock()
                mock_gemini.return_value = mock_instance

                provider = get_ai_provider()

                assert provider == mock_instance
                mock_gemini.assert_called_once()

    def test_get_anthropic_provider(self):
        """Test factory returns Anthropic provider when configured."""
        with patch.dict(os.environ, {'AI_PROVIDER': 'anthropic'}):
            import importlib
            import app.core.config
            importlib.reload(app.core.config)

            with patch('app.services.ai_provider.AnthropicProvider') as mock_anthropic:
                mock_instance = MagicMock()
                mock_anthropic.return_value = mock_instance

                provider = get_ai_provider()

                assert provider == mock_instance
                mock_anthropic.assert_called_once()

    def test_invalid_provider_raises_error(self):
        """Test factory raises error for unknown provider."""
        with patch.dict(os.environ, {'AI_PROVIDER': 'invalid'}):
            import importlib
            import app.core.config
            importlib.reload(app.core.config)

            with pytest.raises(ValueError, match="Unknown AI provider"):
                get_ai_provider()


class TestAIVerificationService:
    """Test the main AI Verification Service."""

    def setup_method(self):
        with patch('app.services.ai_verification.get_ai_provider') as mock_get_provider:
            self.mock_provider = AsyncMock()
            mock_get_provider.return_value = self.mock_provider

            from app.services.ai_verification import AIVerificationService
            self.service = AIVerificationService()

    @pytest.mark.asyncio
    async def test_verify_claim_delegates_to_provider(self):
        """Test that verify_claim delegates to the provider."""
        mock_output = VerificationOutput(
            verdict=VerificationVerdict.SUPPORTED,
            confidence_score=85,
            explanation="Test",
            evidence_status="Test"
        )
        self.mock_provider.verify_claim = AsyncMock(return_value=mock_output)

        claim = ClaimWithEvidence(
            claim_id="test-1",
            claim_text="Test claim",
            citation_text="[1] Test.",
            evidence_passages=["Evidence"],
            publication_title="Test"
        )

        result = await self.service.verify_claim(claim)

        assert result == mock_output
        self.mock_provider.verify_claim.assert_called_once_with(claim)

    @pytest.mark.asyncio
    async def test_verify_batch_delegates_to_provider(self):
        """Test that verify_batch delegates to the provider."""
        mock_outputs = [
            VerificationOutput(verdict=VerificationVerdict.SUPPORTED, confidence_score=85, explanation="Test", evidence_status="Test"),
            VerificationOutput(verdict=VerificationVerdict.PARTIALLY_SUPPORTED, confidence_score=60, explanation="Test", evidence_status="Test"),
        ]
        self.mock_provider.verify_batch = AsyncMock(return_value=mock_outputs)

        claims = [
            ClaimWithEvidence(claim_id="1", claim_text="Claim 1", citation_text="[1]", evidence_passages=["Evidence 1"], publication_title="Paper 1"),
            ClaimWithEvidence(claim_id="2", claim_text="Claim 2", citation_text="[2]", evidence_passages=["Evidence 2"], publication_title="Paper 2"),
        ]

        results = await self.service.verify_batch(claims)

        assert results == mock_outputs
        self.mock_provider.verify_batch.assert_called_once_with(claims)

    @pytest.mark.asyncio
    async def test_close_delegates_to_provider(self):
        """Test that close delegates to the provider."""
        await self.service.close()
        self.mock_provider.close.assert_called_once()