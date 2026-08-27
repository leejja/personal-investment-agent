from app.services.kiwoom import (
    KiwoomAccountBalance,
    KiwoomService,
    KiwoomStockInfo,
    KiwoomStockListItem,
)

# ka10099 mrkt_tp 값. "0"=코스피, "10"=코스닥은 실제 API 호출로 검증된
# 값이다. ETF(8)/ETN(60 등)은 애초에 이 두 semantic method 어디에도
# 없으므로 구조적으로 조회 대상에서 제외된다.
_MRKT_TP_KOSPI = "0"
_MRKT_TP_KOSDAQ = "10"


class KiwoomTools:
    def __init__(self, service: KiwoomService) -> None:
        self.service = service

    async def get_stock_info(
        self,
        stock_code: str,
    ) -> KiwoomStockInfo:
        token = await self.service.get_access_token()

        return await self.service.get_stock_info(
            access_token=token.token,
            stock_code=stock_code,
        )

    async def get_account_balance(
        self,
        query_type: str = "1",
        exchange_type: str = "KRX",
    ) -> KiwoomAccountBalance:
        token = await self.service.get_access_token()

        return await self.service.get_account_balance(
            access_token=token.token,
            query_type=query_type,
            exchange_type=exchange_type,
        )

    async def get_kospi_stock_list(self) -> list[KiwoomStockListItem]:
        token = await self.service.get_access_token()

        return await self.service.get_stock_list(
            access_token=token.token,
            market_code=_MRKT_TP_KOSPI,
        )

    async def get_kosdaq_stock_list(self) -> list[KiwoomStockListItem]:
        token = await self.service.get_access_token()

        return await self.service.get_stock_list(
            access_token=token.token,
            market_code=_MRKT_TP_KOSDAQ,
        )
