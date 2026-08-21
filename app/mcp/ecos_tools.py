from app.services.ecos import EcosService, EcosStatisticPoint


class EcosTools:
    def __init__(self, service: EcosService) -> None:
        self.service = service

    async def get_base_rate(
        self,
        start_date: str,
        end_date: str,
    ) -> list[EcosStatisticPoint]:
        return await self.service.get_statistic(
            statistic_code="722Y001",
            cycle="D",
            start_date=start_date,
            end_date=end_date,
            item_code1="0101000",
        )