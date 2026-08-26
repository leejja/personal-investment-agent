from typing import Any

import httpx
from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    model: str
    finish_reason: str | None = None


class LLMService:
    BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        url = f"{self.BASE_URL}/chat/completions"

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
        }

        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()

        return self._convert_response(data)

    def _convert_response(self, data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices")

        if not choices:
            raise ValueError(f"Unexpected OpenAI response: {data}")

        choice = choices[0]
        message = choice.get("message")

        if not isinstance(message, dict):
            raise TypeError(f"Unexpected OpenAI response: {data}")

        content = message.get("content")

        if not isinstance(content, str):
            raise TypeError(f"Unexpected OpenAI response: {data}")

        return LLMResponse(
            content=content,
            model=data.get("model", ""),
            finish_reason=choice.get("finish_reason"),
        )
