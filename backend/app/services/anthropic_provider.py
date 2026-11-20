"""Anthropic Claude AI provider implementation for VERITAS AI verification (fallback).

Uses the official Anthropic Python SDK.
"""

import asyncio
import logging
from typing import Optional
from anthropic import AsyncAnthropic
from anthropic.types import Message

from app.core.config import settings
from app.services.ai_provider import AIProvider, ClaimWithEvidence, VerificationOutput

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Anthropic Claude AI provider for claim verification (fallback/alternative)."""

    def __init__(self):
        super().__init__()
        self.client: Optional[AsyncAnthropic] = None
        self._initialize_client()

    def _get_model_name(self) -> str:
        """Return the configured Anthropic model name."""
        return settings.CLAUDE_MODEL

    def _initialize_client(self):
        """Initialize the Anthropic client with API key."""
        try:
            self.client = AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=settings.AI_TIMEOUT_SECONDS,
                max_retries=0,  # We handle retries ourselves
            )
            logger.info(f"Initialized Anthropic provider with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            raise

    async def _call_model(self, prompt: str, system_prompt: str) -> str:
        """Call the Anthropic model with the given prompt and system instructions.

        Implements retry logic with exponential backoff for rate limits and transient errors.
        """
        max_retries = settings.AI_MAX_RETRIES
        base_backoff = settings.AI_RETRY_BACKOFF_BASE

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response: Message = await self.client.messages.create(
                    model=self.model_name,
                    max_tokens=1500,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Extract text from response
                if response.content:
                    for block in response.content:
                        if block.type == "text":
                            return block.text

                raise ValueError("Empty response from Anthropic")

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                # Check if we should retry
                is_retryable = any(keyword in error_str for keyword in [
                    "rate limit",
                    "quota",
                    "timeout",
                    "temporary",
                    "unavailable",
                    "503",
                    "429",
                    "internal error",
                    "overloaded",
                    "overloaded_error",
                    "rate_limit_error",
                ])

                if attempt < max_retries and is_retryable:
                    wait_time = base_backoff ** attempt
                    logger.warning(
                        f"Anthropic API call failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Non-retryable error or max retries reached
                logger.error(f"Anthropic verification failed after {attempt + 1} attempts: {e}")
                raise

        raise last_exception or RuntimeError("Max retries exceeded")

    async def close(self):
        """Close the Anthropic client."""
        if self.client:
            await self.client.close()
            self.client = None
        logger.debug("Anthropic provider closed")