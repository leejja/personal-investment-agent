from pydantic import BaseModel

from app.models.evidence import (
    MEASURE_PBR,
    MEASURE_PER,
    MEASURE_ROE,
    EvidenceItemIdentity,
    EvidenceOrigin,
    EvidenceReference,
    EvidenceSource,
)
from app.services.kiwoom import (
    KiwoomAccountBalance,
    KiwoomService,
    KiwoomStockInfo,
    KiwoomStockListItem,
    KiwoomThemeGroup,
    KiwoomThemeStock,
)

_KIWOOM_STOCK_INFO_SOURCE = EvidenceSource(provider="Kiwoom", interface="ka10001")

# ka10099 mrkt_tp 값. "0"=코스피, "10"=코스닥은 실제 API 호출로 검증된
# 값이다. ETF(8)/ETN(60 등)은 애초에 이 두 semantic method 어디에도
# 없으므로 구조적으로 조회 대상에서 제외된다.
_MRKT_TP_KOSPI = "0"
_MRKT_TP_KOSDAQ = "10"


class KiwoomStockInfoWithEvidence(BaseModel):
    """internal carrier(MCP tool이 반환하지 않는다). `evidence`는 ROE / PER / PBR 중
    값이 None이 아닌 것의 reference다. provider가 계산한 비율일 수 있지만 이 시스템은
    그 derivation을 모르므로 SOURCE_REPORTED이며 formula lineage를 만들지 않는다.
    ka10001은 version anchor를 제공하지 않으므로 `version_anchor=None`이다(만들지 않음)."""

    stock_info: KiwoomStockInfo
    evidence: dict[str, EvidenceReference]


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

    async def get_stock_info_with_evidence(
        self,
        stock_code: str,
    ) -> KiwoomStockInfoWithEvidence:
        """`get_stock_info()`와 같은 값에 ROE / PER / PBR evidence reference를 함께
        반환하는 internal 경로. 공개 tool 출력은 바꾸지 않는다."""
        token = await self.service.get_access_token()
        retrieval = await self.service.fetch_stock_info(
            access_token=token.token,
            stock_code=stock_code,
        )
        info = retrieval.stock_info

        evidence: dict[str, EvidenceReference] = {}
        for measure, value in (
            (MEASURE_ROE, info.roe),
            (MEASURE_PER, info.per),
            (MEASURE_PBR, info.pbr),
        ):
            if value is None:
                continue
            evidence[measure] = EvidenceReference(
                identity=EvidenceItemIdentity(
                    entity=info.stock_code,
                    measure=measure,
                    origin=EvidenceOrigin.SOURCE_REPORTED,
                    source=_KIWOOM_STOCK_INFO_SOURCE,
                ),
                retrieved_at=retrieval.retrieved_at,
            )

        return KiwoomStockInfoWithEvidence(stock_info=info, evidence=evidence)

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

    async def get_theme_groups(self) -> list[KiwoomThemeGroup]:
        token = await self.service.get_access_token()

        return await self.service.get_theme_groups(access_token=token.token)

    async def get_theme_stocks(self, theme_code: str) -> list[KiwoomThemeStock]:
        token = await self.service.get_access_token()

        return await self.service.get_theme_stocks(
            access_token=token.token,
            theme_code=theme_code,
        )
