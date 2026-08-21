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