import httpx
import pytest

from app.services.llm import LLMService


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)


@pytest.mark.anyio
async def test_complete_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"

        body = request.content.decode()
        assert '"model":"test-model"' in body
        assert '"role":"user"' in body

        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "테스트 응답입니다.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
            request=request,
        )

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="test-model")

    response = await service.complete(
        messages=[{"role": "user", "content": "삼성전자를 분석해줘"}],
    )

    assert response.content == "테스트 응답입니다."
    assert response.model == "test-model"
    assert response.finish_reason == "stop"


@pytest.mark.anyio
async def test_complete_overrides_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert '"model":"override-model"' in body

        return httpx.Response(
            200,
            json={
                "model": "override-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
            request=request,
        )

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="default-model")

    response = await service.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="override-model",
    )

    assert response.model == "override-model"


@pytest.mark.anyio
async def test_complete_sends_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert '"response_format":{"type":"json_object"}' in body

        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
            },
            request=request,
        )

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="test-model")

    await service.complete(
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
    )


@pytest.mark.anyio
async def test_complete_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="test-model")

    with pytest.raises(httpx.HTTPStatusError):
        await service.complete(
            messages=[{"role": "user", "content": "hello"}],
        )


@pytest.mark.anyio
async def test_complete_raises_on_missing_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "test-model"}, request=request)

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="test-model")

    with pytest.raises(ValueError, match="Unexpected OpenAI response"):
        await service.complete(
            messages=[{"role": "user", "content": "hello"}],
        )


@pytest.mark.anyio
async def test_complete_raises_on_missing_message_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant"}}],
            },
            request=request,
        )

    _mock_transport(monkeypatch, handler)

    service = LLMService(api_key="test-key", model="test-model")

    with pytest.raises(TypeError, match="Unexpected OpenAI response"):
        await service.complete(
            messages=[{"role": "user", "content": "hello"}],
        )
