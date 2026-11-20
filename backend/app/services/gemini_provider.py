"""Gemini AI provider implementation for VERITAS AI verification.

Uses Google's official Gemini API through the google-genai SDK.
"""

import asyncio
import logging
from typing import Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.services.ai_provider import AIProvider, ClaimWithEvidence, VerificationOutput

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Google Gemini AI provider for claim verification."""

    def __init__(self):
        super().__init__()
        self.client: Optional[genai.Client] = None
        self._initialize_client()

    def _get_model_name(self) -> str:
        """Return the configured Gemini model name."""
        return settings.GEMINI_MODEL

    def _initialize_client(self):
        """Initialize the Gemini client with API key."""
        try:
            self.client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    timeout=settings.AI_TIMEOUT_SECONDS * 1000,
                )
            )
            logger.info(f"Initialized Gemini provider with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise

    async def _call_model(self, prompt: str, system_prompt: str) -> str:
        """Call the Gemini model with the given prompt and system instructions.

        Implements retry logic with exponential backoff for rate limits and transient errors.
        """
        max_retries = settings.AI_MAX_RETRIES
        base_backoff = settings.AI_RETRY_BACKOFF_BASE

        # Combine system prompt with user prompt for Gemini
        full_prompt = f"{system_prompt}\n\n{prompt}"

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                # Generate content with the model
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=2048,
                        response_mime_type="application/json",
                    )
                )

                # Extract text from response
                if response.text and response.text.strip():
                    return response.text.strip()

                # Handle case where response might be blocked or empty
                if response.candidates:
                    candidate = response.candidates[0]
                    if candidate.finish_reason == "SAFETY":
                        logger.warning("Gemini response blocked by safety filters")
                        raise ValueError("Response blocked by safety filters")
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if part.text and part.text.strip():
                                return part.text.strip()

                logger.warning(f"Empty response from Gemini (attempt {attempt + 1})")
                raise ValueError("Empty response from Gemini")

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
                    "deadline exceeded",
                    "resource exhausted",
                ])

                if attempt < max_retries and is_retryable:
                    wait_time = base_backoff ** attempt
                    logger.warning(
                        f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Non-retryable error or max retries reached
                logger.error(f"Gemini verification failed after {attempt + 1} attempts: {e}")
                raise

        raise last_exception or RuntimeError("Max retries exceeded")

    async def close(self):
        """Close the Gemini client."""
        self.client = None
        logger.debug("Gemini provider closed")