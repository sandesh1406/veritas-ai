"""AI Verification Service for VERITAS AI.

This module provides the main entry point for AI-powered claim verification,
using the configured AI provider (Gemini or Anthropic) through the provider abstraction.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from app.core.config import settings
from app.services.ai_provider import (
    AIProvider,
    ClaimWithEvidence,
    VerificationOutput,
    get_ai_provider,
)
from app.models.schemas import VerificationVerdict

logger = logging.getLogger(__name__)


@dataclass
class BatchVerificationResult:
    """Result of batch verification with metadata."""
    verifications: List[VerificationOutput]
    total_claims: int
    successful: int
    failed: int
    errors: List[str]


class AIVerificationService:
    """Main service for verifying claims against evidence using configured AI provider."""

    def __init__(self):
        self.provider: AIProvider = get_ai_provider()
        logger.info(f"Initialized AI Verification Service with provider: {settings.AI_PROVIDER}")

    async def verify_claim(self, claim_data: ClaimWithEvidence) -> VerificationOutput:
        """Verify a single claim against its evidence."""
        return await self.provider.verify_claim(claim_data)

    async def verify_batch(
        self,
        claims: List[ClaimWithEvidence],
        max_concurrent: int = 3
    ) -> BatchVerificationResult:
        """Verify multiple claims with controlled concurrency.

        Args:
            claims: List of claims with evidence to verify
            max_concurrent: Maximum concurrent verifications

        Returns:
            BatchVerificationResult with all verifications and metadata
        """
        if not claims:
            return BatchVerificationResult(
                verifications=[],
                total_claims=0,
                successful=0,
                failed=0,
                errors=[]
            )

        semaphore = asyncio.Semaphore(max_concurrent)
        errors = []

        async def verify_with_semaphore(claim: ClaimWithEvidence) -> VerificationOutput:
            async with semaphore:
                try:
                    return await self.provider.verify_claim(claim)
                except Exception as e:
                    logger.error(f"Verification failed for claim {claim.claim_id}: {e}")
                    errors.append(f"Claim {claim.claim_id}: {str(e)}")
                    # Return NEEDS_REVIEW as fallback
                    return VerificationOutput(
                        verdict=VerificationVerdict.NEEDS_REVIEW,
                        confidence_score=0.0,
                        explanation=f"Verification failed due to error: {str(e)}",
                        evidence_status="Error during AI processing"
                    )

        # Run all verifications concurrently with semaphore
        results = await asyncio.gather(
            *[verify_with_semaphore(claim) for claim in claims],
            return_exceptions=False
        )

        successful = sum(1 for r in results if r.verdict != VerificationVerdict.NEEDS_REVIEW or r.confidence_score > 0)
        failed = len(results) - successful

        return BatchVerificationResult(
            verifications=results,
            total_claims=len(claims),
            successful=successful,
            failed=failed,
            errors=errors
        )

    async def verify_claims_for_document(
        self,
        claims: List[ClaimWithEvidence],
        progress_callback: Optional[callable] = None
    ) -> List[VerificationOutput]:
        """Verify claims for a document with optional progress tracking.

        This is a convenience method that wraps verify_batch with progress reporting.

        Args:
            claims: List of claims with evidence to verify
            progress_callback: Optional callback(claim_id, verdict, progress_percent)

        Returns:
            List of VerificationOutput in the same order as input claims
        """
        if not claims:
            return []

        semaphore = asyncio.Semaphore(3)
        results = [None] * len(claims)
        completed = 0
        errors = []

        async def verify_with_progress(index: int, claim: ClaimWithEvidence):
            nonlocal completed
            async with semaphore:
                try:
                    result = await self.provider.verify_claim(claim)
                    results[index] = result
                except Exception as e:
                    logger.error(f"Verification failed for claim {claim.claim_id}: {e}")
                    errors.append(f"Claim {claim.claim_id}: {str(e)}")
                    results[index] = VerificationOutput(
                        verdict=VerificationVerdict.NEEDS_REVIEW,
                        confidence_score=0.0,
                        explanation=f"Verification failed due to error: {str(e)}",
                        evidence_status="Error during AI processing"
                    )
                finally:
                    completed += 1
                    if progress_callback:
                        progress_percent = int((completed / len(claims)) * 100)
                        verdict = results[index].verdict if results[index] else "ERROR"
                        await progress_callback(claim.claim_id, verdict, progress_percent)

        await asyncio.gather(*[
            verify_with_progress(i, claim) for i, claim in enumerate(claims)
        ])

        if errors:
            logger.warning(f"Completed with {len(errors)} errors: {errors}")

        return results

    async def close(self):
        """Close the AI provider connections."""
        await self.provider.close()


async def create_verification_service() -> AIVerificationService:
    """Factory function to create and initialize the verification service."""
    return AIVerificationService()