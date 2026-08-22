from app.services.kiwoom import (
    KiwoomService,
    KiwoomStockInfo,
)


class KiwoomTools:
    def __init__(self, service: KiwoomService) -> None:
        self.service = service

    async def get_stock_info(
        self,
        stock_code: str,
    ) -> KiwoomStockInfo:
        token = await self.service.issue_access_token()

        return await self.service.get_stock_info(
            access_token=token.token,
            stock_code=stock_code,
        )