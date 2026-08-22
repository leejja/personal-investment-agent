from app.services.kiwoom import (
    KiwoomAccountBalance,
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

    async def get_account_balance(
        self,
        query_type: str = "1",
        exchange_type: str = "KRX",
    ) -> KiwoomAccountBalance:
        token = await self.service.issue_access_token()

        return await self.service.get_account_balance(
            access_token=token.token,
            query_type=query_type,
            exchange_type=exchange_type,
        )