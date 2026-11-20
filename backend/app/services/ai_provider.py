"""AI Provider abstraction for VERITAS AI verification.

This module provides a common interface for different AI providers (Gemini, Anthropic)
to enable configurable AI-powered claim verification.
"""

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from app.models.schemas import VerificationVerdict
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ClaimWithEvidence:
    """Claim data with associated evidence for verification."""
    claim_id: str
    claim_text: str
    citation_text: str
    evidence_passages: List[str]
    publication_title: str


@dataclass
class VerificationOutput:
    """Structured verification result from AI provider."""
    verdict: VerificationVerdict
    confidence_score: float  # 0-100
    explanation: str
    evidence_status: str


class AIProvider(ABC):
    """Abstract base class for AI verification providers."""

    # Shared system prompt across all providers
    SYSTEM_PROMPT = """You are a scientific claim verification expert. Your task is to compare a scientific claim against retrieved evidence passages from cited publications and determine the verification verdict.

VERDICTS (exactly one):
- SUPPORTED: The evidence directly and fully supports the claim
- PARTIALLY_SUPPORTED: The evidence supports some aspects but not all, or supports a weaker version
- UNSUPPORTED: The evidence does not support the claim (neither confirms nor contradicts)
- CONTRADICTORY: The evidence directly contradicts the claim
- POTENTIALLY_OUTDATED: The claim was supported at publication time but newer evidence suggests otherwise
- NEEDS_REVIEW: Insufficient evidence retrieved, evidence is inaccessible, or claim cannot be evaluated with available information

RULES:
1. ONLY use the provided evidence passages. Do not use external knowledge.
2. If no evidence passages are provided or they are inaccessible, return NEEDS_REVIEW.
3. Be conservative: when in doubt, use NEEDS_REVIEW or PARTIALLY_SUPPORTED.
4. Confidence score 0-100: how certain you are given the evidence quality and relevance.
5. Cite specific evidence passages in your explanation.
6. Return ONLY valid JSON matching the specified schema."""

    VERIFICATION_PROMPT = """Claim: {claim_text}

Cited Source: {citation_text}

Publication: {publication_title}

Retrieved Evidence Passages:
{evidence_passages}

Determine the verification verdict. Return JSON:
{{
  "verdict": "VERDICT_VALUE",
  "confidence_score": 0-100,
  "explanation": "Detailed reasoning citing specific evidence passages",
  "evidence_status": "Description of evidence availability and quality"
}}"""

    def __init__(self):
        self.model_name = self._get_model_name()

    @abstractmethod
    def _get_model_name(self) -> str:
        """Return the model name for this provider."""
        pass

    @abstractmethod
    async def _call_model(self, prompt: str, system_prompt: str) -> str:
        """Call the AI model and return the raw text response."""
        pass

    def _format_evidence(self, evidence_passages: List[str]) -> str:
        """Format evidence passages for the prompt. Treat as untrusted input."""
        if not evidence_passages:
            return "[NO EVIDENCE RETRIEVED - Full text not accessible]"

        # Sanitize and truncate evidence passages
        sanitized = []
        for i, passage in enumerate(evidence_passages[:5]):
            # Truncate and strip control characters
            cleaned = "".join(char for char in passage if char.isprintable() or char in "\n\t")
            sanitized.append(f"[Passage {i+1}]: {cleaned[:2000]}")

        return "\n\n".join(sanitized)

    def _build_prompt(self, claim_data: ClaimWithEvidence) -> str:
        """Build the verification prompt from claim data."""
        evidence_text = self._format_evidence(claim_data.evidence_passages)

        return self.VERIFICATION_PROMPT.format(
            claim_text=claim_data.claim_text,
            citation_text=claim_data.citation_text,
            publication_title=claim_data.publication_title,
            evidence_passages=evidence_text
        )

    def _parse_response(self, content: str) -> VerificationOutput:
        """Parse JSON response from AI model with strict validation."""
        # Extract JSON if wrapped in markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        if not content:
            raise ValueError("Empty response from AI")

        # Try to parse JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Response content: {content[:500]}")
            raise ValueError(f"Invalid JSON response from AI: {e}")

        # Validate required fields
        required_fields = ["verdict", "confidence_score", "explanation", "evidence_status"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field in AI response: {field}")

        # Validate verdict - must be one of the six allowed values
        try:
            verdict = VerificationVerdict(result["verdict"])
        except ValueError:
            valid_verdicts = [v.value for v in VerificationVerdict]
            raise ValueError(f"Invalid verdict '{result['verdict']}'. Must be one of: {valid_verdicts}")

        # Validate confidence score - must be finite number 0-100
        try:
            confidence = float(result["confidence_score"])
        except (TypeError, ValueError):
            raise ValueError(f"Confidence score must be a number, got: {result['confidence_score']}")

        # Check for NaN and infinity
        if math.isnan(confidence) or math.isinf(confidence):
            raise ValueError(f"Confidence score must be finite, got: {confidence}")

        if not 0 <= confidence <= 100:
            logger.warning(f"Confidence score {confidence} out of range, clamping to 0-100")
            confidence = max(0.0, min(100.0, confidence))

        # Validate explanation and evidence_status are strings
        explanation = str(result["explanation"]) if result["explanation"] else ""
        evidence_status = str(result["evidence_status"]) if result["evidence_status"] else ""

        if not explanation:
            raise ValueError("Explanation cannot be empty")

        return VerificationOutput(
            verdict=verdict,
            confidence_score=confidence,
            explanation=explanation,
            evidence_status=evidence_status
        )

    async def verify_claim(self, claim_data: ClaimWithEvidence) -> VerificationOutput:
        """Verify a single claim against its evidence.

        Returns NEEDS_REVIEW immediately if no evidence passages provided.
        """
        # Return NEEDS_REVIEW immediately when evidence is missing
        if not claim_data.evidence_passages or all(not p.strip() for p in claim_data.evidence_passages):
            logger.info(f"Claim {claim_data.claim_id}: No evidence passages provided, returning NEEDS_REVIEW")
            return VerificationOutput(
                verdict=VerificationVerdict.NEEDS_REVIEW,
                confidence_score=0.0,
                explanation="No evidence passages were retrieved or provided for this claim. The cited source could not be accessed or contained no relevant content.",
                evidence_status="No evidence retrieved"
            )

        prompt = self._build_prompt(claim_data)

        try:
            response_text = await self._call_model(prompt, self.SYSTEM_PROMPT)
            return self._parse_response(response_text)

        except ValueError as e:
            # Validation errors - return NEEDS_REVIEW
            logger.error(f"AI response validation failed for claim {claim_data.claim_id}: {e}")
            return VerificationOutput(
                verdict=VerificationVerdict.NEEDS_REVIEW,
                confidence_score=0.0,
                explanation=f"AI response validation failed: {str(e)}",
                evidence_status="Invalid AI response"
            )
        except Exception as e:
            logger.error(f"AI verification failed for claim {claim_data.claim_id}: {e}")
            # Fallback to NEEDS_REVIEW on any error
            return VerificationOutput(
                verdict=VerificationVerdict.NEEDS_REVIEW,
                confidence_score=0.0,
                explanation=f"Verification failed due to error: {str(e)}",
                evidence_status="Error during AI processing"
            )

    async def verify_batch(self, claims: List[ClaimWithEvidence]) -> List[VerificationOutput]:
        """Verify multiple claims with bounded concurrency and rate-limit awareness."""
        if not claims:
            return []

        # Bounded concurrency - max 3 concurrent requests
        semaphore = asyncio.Semaphore(3)
        results: List[Optional[VerificationOutput]] = [None] * len(claims)

        async def verify_with_semaphore(index: int, claim: ClaimWithEvidence) -> None:
            async with semaphore:
                # Small delay to avoid hitting rate limits
                if index > 0:
                    await asyncio.sleep(0.1)
                try:
                    results[index] = await self.verify_claim(claim)
                except Exception as e:
                    logger.error(f"Batch verification failed for claim {claim.claim_id}: {e}")
                    results[index] = VerificationOutput(
                        verdict=VerificationVerdict.NEEDS_REVIEW,
                        confidence_score=0.0,
                        explanation=f"Batch verification error: {str(e)}",
                        evidence_status="Batch processing error"
                    )

        # Execute all verifications concurrently with semaphore
        await asyncio.gather(*[
            verify_with_semaphore(i, claim) for i, claim in enumerate(claims)
        ])

        return results  # type: ignore

    @abstractmethod
    async def close(self):
        """Close any open connections."""
        pass


def get_ai_provider() -> AIProvider:
    """Factory function to create the configured AI provider."""
    provider_name = settings.AI_PROVIDER.lower()

    if provider_name == "gemini":
        from app.services.gemini_provider import GeminiProvider
        return GeminiProvider()
    elif provider_name == "anthropic":
        from app.services.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider_name}. Supported: 'gemini', 'anthropic'")