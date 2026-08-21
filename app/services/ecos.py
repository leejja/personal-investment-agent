from typing import Any

import httpx
from pydantic import BaseModel


class EcosStatisticPoint(BaseModel):
    statistic_code: str
    statistic_name: str
    item_code1: str
    item_name1: str
    unit: str | None
    time: str
    value: float


class EcosService:
    BASE_URL = "https://ecos.bok.or.kr/api"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

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
        url = self._build_statistic_url(
            statistic_code=statistic_code,
            cycle=cycle,
            start_date=start_date,
            end_date=end_date,
            item_code1=item_code1,
            item_code2=item_code2,
            item_code3=item_code3,
            item_code4=item_code4,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

        data = response.json()

        statistic_search = data.get("StatisticSearch")
        if statistic_search is None:
            raise ValueError(f"Unexpected ECOS response: {data}")

        rows = statistic_search.get("row", [])

        return [self._convert_row(row) for row in rows]

    def _build_statistic_url(
        self,
        statistic_code: str,
        cycle: str,
        start_date: str,
        end_date: str,
        item_code1: str,
        item_code2: str | None = None,
        item_code3: str | None = None,
        item_code4: str | None = None,
    ) -> str:
        parts = [
            self.BASE_URL,
            "StatisticSearch",
            self.api_key,
            "json",
            "kr",
            "1",
            "100",
            statistic_code,
            cycle,
            start_date,
            end_date,
            item_code1,
        ]

        for item_code in (item_code2, item_code3, item_code4):
            if item_code is not None:
                parts.append(item_code)

        return "/".join(parts)

    def _convert_row(self, row: dict[str, Any]) -> EcosStatisticPoint:
        return EcosStatisticPoint(
            statistic_code=row["STAT_CODE"],
            statistic_name=row["STAT_NAME"],
            item_code1=row["ITEM_CODE1"],
            item_name1=row["ITEM_NAME1"],
            unit=row.get("UNIT_NAME"),
            time=row["TIME"],
            value=float(row["DATA_VALUE"]),
        )