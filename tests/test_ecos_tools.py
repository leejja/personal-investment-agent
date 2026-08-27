import pytest

from app.mcp.ecos_tools import EcosTools
from app.services.ecos import EcosStatisticPoint


class FakeEcosService:
    async def get_statistic(
        self,
        statistic_code: str,
        cycle: str,
        start_date: str,
        end_date: str,
        item_code1: str,
        item_code2: str | None = None,
        item_code3: str | None = None,
        item_code4: str | None = None,
    ) -> list[EcosStatisticPoint]:
        assert statistic_code == "722Y001"
        assert cycle == "D"
        assert start_date == "20260818"
        assert end_date == "20260821"
        assert item_code1 == "0101000"

        return [
            EcosStatisticPoint(
                statistic_code="722Y001",
                statistic_name="1.3.1. 한국은행 기준금리 및 여수신금리",
                item_code1="0101000",
                item_name1="한국은행 기준 금리",
                unit="연%",
                time="20260821",
                value=2.75,
            )
        ]


@pytest.mark.anyio
async def test_get_base_rate() -> None:
    tools = EcosTools(service=FakeEcosService())

    points = await tools.get_base_rate(
        start_date="20260818",
        end_date="20260821",
    )

    assert len(points) == 1
    assert points[0].value == 2.75


class FakeExchangeRateEcosService:
    async def get_statistic(
        self,
        statistic_code: str,
        cycle: str,
        start_date: str,
        end_date: str,
        item_code1: str,
        item_code2: str | None = None,
        item_code3: str | None = None,
        item_code4: str | None = None,
    ) -> list[EcosStatisticPoint]:
        assert statistic_code == "731Y001"
        assert cycle == "D"
        assert start_date == "20260818"
        assert end_date == "20260821"
        assert item_code1 == "0000001"

        return [
            EcosStatisticPoint(
                statistic_code="731Y001",
                statistic_name="3.1.1.1. 주요국 통화의 대원화환율",
                item_code1="0000001",
                item_name1="원/미국달러(매매기준율)",
                unit="원",
                time="20260821",
                value=1383.1,
            )
        ]


@pytest.mark.anyio
async def test_get_exchange_rate() -> None:
    tools = EcosTools(service=FakeExchangeRateEcosService())

    points = await tools.get_exchange_rate(
        start_date="20260818",
        end_date="20260821",
    )

    assert len(points) == 1
    assert points[0].value == 1383.1


class FakeKospiEcosService:
    async def get_statistic(
        self,
        statistic_code: str,
        cycle: str,
        start_date: str,
        end_date: str,
        item_code1: str,
        item_code2: str | None = None,
        item_code3: str | None = None,
        item_code4: str | None = None,
    ) -> list[EcosStatisticPoint]:
        assert statistic_code == "802Y001"
        assert cycle == "D"
        assert start_date == "20260818"
        assert end_date == "20260821"
        assert item_code1 == "0001000"

        return [
            EcosStatisticPoint(
                statistic_code="802Y001",
                statistic_name="1.5.1.1. 주식시장(일)",
                item_code1="0001000",
                item_name1="KOSPI지수",
                unit="1980.01.04=100",
                time="20260821",
                value=6808.21,
            )
        ]


@pytest.mark.anyio
async def test_get_kospi_index() -> None:
    tools = EcosTools(service=FakeKospiEcosService())

    points = await tools.get_kospi_index(
        start_date="20260818",
        end_date="20260821",
    )

    assert len(points) == 1
    assert points[0].value == 6808.21


class FakeKosdaqEcosService:
    async def get_statistic(
        self,
        statistic_code: str,
        cycle: str,
        start_date: str,
        end_date: str,
        item_code1: str,
        item_code2: str | None = None,
        item_code3: str | None = None,
        item_code4: str | None = None,
    ) -> list[EcosStatisticPoint]:
        assert statistic_code == "802Y001"
        assert cycle == "D"
        assert start_date == "20260818"
        assert end_date == "20260821"
        assert item_code1 == "0089000"

        return [
            EcosStatisticPoint(
                statistic_code="802Y001",
                statistic_name="1.5.1.1. 주식시장(일)",
                item_code1="0089000",
                item_name1="KOSDAQ지수",
                unit="1996.07.01=1000",
                time="20260821",
                value=826.87,
            )
        ]


@pytest.mark.anyio
async def test_get_kosdaq_index() -> None:
    tools = EcosTools(service=FakeKosdaqEcosService())

    points = await tools.get_kosdaq_index(
        start_date="20260818",
        end_date="20260821",
    )

    assert len(points) == 1
    assert points[0].value == 826.87