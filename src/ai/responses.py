"""Bearer-authenticated Responses API for subscription gateways."""

import httpx
from openai import AsyncOpenAI

from .client import AIClient, _resolve_api_key
from .tokens import record_usage
from ..models import AIConfig


class ResponsesClient(AIClient):
    def __init__(self, config: AIConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=_resolve_api_key(config), base_url=config.base_url,
            max_retries=0, timeout=httpx.Timeout(300, connect=20),
        )

    async def complete(self, system: str, user: str, temperature=None, max_tokens=None) -> str:
        # Subscription gateways require streaming and reject sampling/token limits.
        stream = await self.client.responses.create(
            model=self.config.model, instructions=system,
            input=[{"role": "user", "content": user}], store=False, stream=True,
        )
        async with stream:
            async for event in stream:
                if event.type in {"response.failed", "response.incomplete", "error"}:
                    raise RuntimeError("Responses inference failed; partial output discarded.")
                if event.type == "response.completed":
                    response = event.response
                    if response.status != "completed" or response.error is not None:
                        raise RuntimeError("Invalid Responses terminal event.")
                    if not response.output_text.strip():
                        raise RuntimeError("Empty Responses output.")
                    if response.usage is not None:
                        record_usage("openai", input_tokens=response.usage.input_tokens,
                                     output_tokens=response.usage.output_tokens)
                    return response.output_text
        raise RuntimeError("Responses stream ended without completion; partial output discarded.")
