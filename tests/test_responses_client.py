"""Responses gateway completion and stream failure contracts."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.client import _create_single_client
from src.models import AIConfig


@pytest.mark.parametrize("terminal", ["response.completed", "response.failed", "response.incomplete", None])
def test_gateway_requires_successful_terminal_event(monkeypatch, terminal):
    monkeypatch.setenv("GATEWAY_KEY", "test-key")
    config = AIConfig(provider="openai", model="gateway-model", api_mode="responses",
                      base_url="http://gateway/v1", api_key_env="GATEWAY_KEY")
    response = SimpleNamespace(status="completed", error=None, output_text="OK", usage=None)
    events = [SimpleNamespace(type="response.output_text.delta", delta="partial")]
    if terminal:
        events.append(SimpleNamespace(type=terminal, response=response))
    stream = MagicMock()
    stream.__aenter__ = AsyncMock(return_value=stream)
    stream.__aexit__ = AsyncMock(return_value=False)
    stream.__aiter__.return_value = events
    with patch("src.ai.responses.AsyncOpenAI") as sdk:
        sdk.return_value.responses.create = AsyncMock(return_value=stream)
        client = _create_single_client(config)
        if terminal == "response.completed":
            assert asyncio.run(client.complete("Instructions", "Input", 0.3, 100)) == "OK"
        else:
            with pytest.raises(RuntimeError):
                asyncio.run(client.complete("Instructions", "Input"))
        sdk.return_value.responses.create.assert_awaited_once_with(
            model="gateway-model", instructions="Instructions",
            input=[{"role": "user", "content": "Input"}], stream=True, store=False,
        )
