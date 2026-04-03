import json

import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class LLMClient:
    """Client for Anthropic Claude API with structured legal reasoning."""

    def __init__(self):
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._max_tokens = 4096

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze(self, system_prompt: str, user_prompt: str) -> dict:
        logger.info("llm_analyze_start", model=self._model)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        result = {
            "content": content,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": response.model,
            "stop_reason": response.stop_reason,
        }

        logger.info(
            "llm_analyze_complete",
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
        )
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def quick_completion(self, prompt: str, max_tokens: int = 256) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def structured_analysis(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict,
    ) -> dict:
        """Request structured JSON output from the LLM."""
        schema_instruction = f"\n\nYou MUST respond with valid JSON matching this schema:\n```json\n{json.dumps(output_schema, indent=2)}\n```"

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt + schema_instruction,
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        # Extract JSON from response
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("structured_analysis_parse_failed", content=content[:200])
            return {"raw_content": content}
