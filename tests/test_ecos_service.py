import httpx
import pytest

from app.services.ecos import EcosService


def test_build_statistic_url_with_item_code1_only() -> None:
    service = EcosService(api_key="test-key")

    url = service._build_statistic_url(
        statistic_code="722Y001",
        cycle="D",
        start_date="20260801",
        end_date="20260821",
        item_code1="0101000",
    )

    assert url == (
        "https://ecos.bok.or.kr/api/"
        "StatisticSearch/"
        "test-key/"
        "json/"
        "kr/"
        "1/"
        "100/"
        "722Y001/"
        "D/"
        "20260801/"
        "20260821/"
        "0101000"
    )


def test_build_statistic_url_with_multiple_item_codes() -> None:
    service = EcosService(api_key="test-key")

    url = service._build_statistic_url(
        statistic_code="TEST001",
        cycle="M",
        start_date="202601",
        end_date="202608",
        item_code1="ITEM1",
        item_code2="ITEM2",
        item_code3="ITEM3",
        item_code4="ITEM4",
    )

    assert url.endswith(
        "/TEST001/M/202601/202608/ITEM1/ITEM2/ITEM3/ITEM4"
    )


@pytest.mark.anyio
async def test_get_statistic_returns_rows(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "StatisticSearch": {
                    "row": [
                        {
                            "STAT_CODE": "722Y001",
                            "STAT_NAME": "테스트 통계",
                            "ITEM_CODE1": "0101000",
                            "ITEM_NAME1": "테스트 항목",
                            "TIME": "20260821",
                            "DATA_VALUE": "2.50",
                            "UNIT_NAME": "%",
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    service = EcosService(api_key="test-key")

    rows = await service.get_statistic(
        statistic_code="722Y001",
        cycle="D",
        start_date="20260821",
        end_date="20260821",
        item_code1="0101000",
    )

    assert len(rows) == 1
    assert rows[0].value == 2.50

    assert len(rows) == 1

    point = rows[0]

    assert point.statistic_code == "722Y001"
    assert point.statistic_name == "테스트 통계"
    assert point.item_code1 == "0101000"
    assert point.item_name1 == "테스트 항목"
    assert point.unit == "%"
    assert point.time == "20260821"
    assert point.value == 2.50


@pytest.mark.anyio
async def test_get_statistic_raises_on_http_error(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    service = EcosService(api_key="test-key")

    with pytest.raises(httpx.HTTPStatusError):
        await service.get_statistic(
            statistic_code="722Y001",
            cycle="D",
            start_date="20260821",
            end_date="20260821",
            item_code1="0101000",
        )


@pytest.mark.anyio
async def test_get_statistic_raises_on_unexpected_response(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"RESULT": {"CODE": "ERROR"}},
        )

    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    service = EcosService(api_key="test-key")

    with pytest.raises(ValueError):
        await service.get_statistic(
            statistic_code="722Y001",
            cycle="D",
            start_date="20260821",
            end_date="20260821",
            item_code1="0101000",
        )