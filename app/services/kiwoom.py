import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

# Kiwoom access token(expires_dt)의 timezone 정책
#
# Kiwoom OAuth 응답의 expires_dt("YYYYMMDDHHMMSS")에는 timezone offset이
# 없다. 공식 API 명세에서도 이를 명시적으로 확인하지 못했다. 이 프로젝트는
# 한국 시장 데이터를 다루는 다른 영역(ECOS 조회 기준일 등, 2026-08-22
# dev-log 9절 참고)에서 이미 명시적으로 KST(Asia/Seoul)를 기준 timezone으로
# 채택하고 있으므로, expires_dt도 동일한 프로젝트 관례를 그대로 적용해
# KST로 해석한다. 공식 Kiwoom 명세에서 timezone이 명확히 확인되면
# 재검토한다.
_KST = ZoneInfo("Asia/Seoul")

# 만료 시각 자체에 대한 불확실성(timezone 오차 등)을 흡수하기 위한
# 값이 아니다 — timezone은 위 정책으로 명시적으로 고정한다. 이 margin은
# "만료 직전에 캐시된 토큰을 반환했는데 실제 API 요청이 도달하기 전에
# 만료되어 버리는" race condition과 네트워크 지연만을 방어하기 위한
# 값이다. 실측 유효기간이 약 18시간대로 넉넉해(2026-08-27 dev-log 참고),
# 이 정도 margin이 재발급 빈도에 미치는 영향은 무시할 만하다.
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

# UX-01 Theme catalog(ka90001) instance-level 캐시의 TTL. 이 값은 "테마
# 분류가 금융적으로 며칠간 유효하다"는 투자 판단이 아니라, "Kiwoom이
# 제공하는 테마 메타데이터(테마 목록 자체)를 얼마나 자주 다시 조회할
# 것인가"를 뜻하는 순수 API/metadata refresh 정책이다. 실측 결과
# 테마 카탈로그는 KRX 대분류(ka10101)보다 훨씬 세분화돼 있지만 그만큼
# 자주 개편되는 종류의 데이터는 아니라고 판단해(개별 종목 시세처럼
# 실시간으로 바뀌는 값이 아님), 하루 단위로 넉넉히 잡았다. 종목 편입/
# 편출 자체가 하루 안에 여러 번 바뀔 이유가 없다는 가정에 기반한
# 값이며, 실제 개편 주기를 관측하지 못했으므로 근거가 강한 값은 아니다.
# 즉 이 값은 확정된 사양이 아니라 현재의 잠정적인 operational refresh
# 정책이다 — 실제 개편 주기가 이후 관측되면(예상보다 자주 또는 훨씬
# 드물게 바뀜) 그에 맞춰 조정할 수 있다.
THEME_CATALOG_CACHE_TTL = timedelta(hours=24)

# ka90001(테마그룹별요청) 전체 카탈로그 조회용 고정 파라미터. qry_tp="0"
# (전체검색)이면 date_tp/flu_pl_amt_tp/stex_tp 값 자체는 반환되는 테마
# 목록에 영향을 주지 않음을 실측으로 확인했다(2026-08-28 UX-01 조사) —
# 다만 API가 이 필드들을 필수로 요구하므로 유효한 값을 채워 넣는다.
_THEME_GROUP_QUERY_ALL = "0"
_THEME_GROUP_DATE_TP = "10"
_THEME_GROUP_FLU_PL_AMT_TP = "1"
_THEME_GROUP_STEX_TP = "1"

# ka90002(테마구성종목요청) 조회용 고정 파라미터. stex_tp="1"(KRX)로
# 통합하고, date_tp는 멤버십 자체와 무관한 수익률 계산 기준일이라
# 실측에 사용한 기본값을 그대로 둔다.
_THEME_STOCK_STEX_TP = "1"
_THEME_STOCK_DATE_TP = "2"


class KiwoomAccessToken(BaseModel):
    expires_dt: str
    token_type: str
    token: str


class KiwoomApiResponse(BaseModel):
    data: dict[str, Any]
    cont_yn: str | None = None
    next_key: str | None = None


class KiwoomStockInfo(BaseModel):
    stock_code: str
    stock_name: str

    current_price: int
    change: int
    change_rate: float
    trading_volume: int

    per: float | None
    pbr: float | None
    roe: float | None
    eps: int | None
    bps: int | None

    high_250d: int | None
    low_250d: int | None


class KiwoomStockInfoRetrieval(BaseModel):
    """internal carrier — 공개 반환 모델(`KiwoomStockInfo`)을 바꾸지 않고 ka10001 응답
    수신 시각을 함께 전달한다. `retrieved_at`은 runtime retrieval 시각이며 provider event
    time / available_at이 아니다. MCP tool이 반환하지 않는다."""

    stock_info: KiwoomStockInfo
    retrieved_at: datetime


class KiwoomAccountPosition(BaseModel):
    stock_code: str
    stock_name: str

    quantity: int
    tradable_quantity: int

    average_price: int
    current_price: int

    purchase_amount: int
    evaluation_amount: int

    profit_loss: int
    return_rate: float
    portfolio_weight: float


class KiwoomAccountBalance(BaseModel):
    total_purchase_amount: int
    total_evaluation_amount: int
    total_profit_loss: int
    total_return_rate: float

    estimated_asset_amount: int | None
    total_loan_amount: int | None
    total_credit_loan_amount: int | None
    total_credit_short_amount: int | None

    positions: list[KiwoomAccountPosition]


class KiwoomStockListItem(BaseModel):
    symbol: str
    name: str

    # market_name은 Kiwoom 원본 marketName을 그대로 보존한다("거래소"/
    # "코스닥" 등). KOSPI/KOSDAQ 구분 자체는 이 필드를 파싱해서가 아니라
    # 호출한 mrkt_tp(어느 메서드로 조회했는지)로 이미 알 수 있으므로,
    # Service 레이어는 Discovery의 MarketFilter 같은 상위 개념을 몰라도
    # 되게 raw 값만 정규화해 전달한다.
    market_name: str
    sector_name: str  # upName
    size_name: str  # upSizeName

    listed_shares: int  # listCount
    last_price: int  # lastPrice

    # 관리종목/투자유의/거래정지 여부를 이 필드들이 어떻게 나타내는지
    # 아직 실측으로 확인하지 못했다(정상 종목의 값만 관측함). 그래서
    # 해석하지 않고 원문 그대로 보존한다 — 실제 flagged 값이 확인되면
    # 그때 구조적으로 해석한다.
    audit_info: str  # auditInfo
    order_warning: str  # orderWarning


class KiwoomThemeGroup(BaseModel):
    """ka90001(테마그룹별요청) 응답 1건. 대표 종목 2개(main_stk)는 실제
    응답에 포함돼 있지만 전체 멤버십이 아니라 사람이 읽는 요약 텍스트일
    뿐이라(예: "LB세미콘, 네패스") 구조화해 보존하지 않는다 — 실제
    멤버십은 항상 ka90002(get_theme_stocks)로 별도 조회한다."""

    theme_code: str  # thema_grp_cd
    theme_name: str  # thema_nm
    stock_count: int  # stk_num


class KiwoomThemeStock(BaseModel):
    """ka90002(테마구성종목요청) 응답 1건 — 테마에 속한 종목 하나."""

    stock_code: str  # stk_cd
    stock_name: str  # stk_nm


class KiwoomService:
    REAL_BASE_URL = "https://api.kiwoom.com"
    MOCK_BASE_URL = "https://mockapi.kiwoom.com"

    def __init__(
        self,
        app_key: str,
        secret_key: str,
        base_url: str = REAL_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        self.app_key = app_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # instance-level 캐시. 여러 KiwoomService 인스턴스나 프로세스 간에
        # 공유하는 전역/singleton 캐시가 아니다 — 이 프로젝트의 모든
        # 호출자(demo 스크립트, MCP server, Supervisor)는 이미 인스턴스
        # 하나를 만들어 계속 재사용하는 패턴이라 이걸로 충분하다.
        self._cached_token: KiwoomAccessToken | None = None
        self._token_lock = asyncio.Lock()

        # UX-01 테마 카탈로그(ka90001) instance-level 캐시. access token
        # 캐시와 의미가 다르다 — token cache는 인증 상태를, 이 캐시는
        # Kiwoom이 제공하는 "테마 목록" 외부 메타데이터를 재사용하기
        # 위한 것이다. Analysis Snapshot Store(app/api/snapshot_store.py,
        # UX-04)와도 목적이 다르다: 이쪽은 API/UI request lifecycle이
        # 아니라 Kiwoom 외부 데이터의 refresh 주기를 다룬다. 동시성
        # 보호(lock)는 두지 않았다 — token 캐시와 달리 동시 cache-miss가
        # 나도 최악의 경우 ka90001을 몇 차례 중복 호출하는 정도이고,
        # 실제로 관측된 문제가 아니라 예방적으로 lock을 추가하지 않는다
        # (dev-log 참고).
        self._theme_catalog_cache: list[KiwoomThemeGroup] | None = None
        self._theme_catalog_cached_at: datetime | None = None

    async def get_access_token(
        self,
        *,
        force_refresh: bool = False,
    ) -> KiwoomAccessToken:
        # 캐시가 유효하면 락 없이 바로 반환한다(매 호출마다 락을 잡지
        # 않기 위한 빠른 경로).
        if not force_refresh and self._is_cached_token_valid():
            assert self._cached_token is not None
            return self._cached_token

        async with self._token_lock:
            # 락을 기다리는 동안 다른 coroutine이 이미 갱신했을 수 있으므로
            # 재확인한다(double-checked locking) — 그래야 동시에 여러
            # coroutine이 캐시 없음을 보고 각자 재발급을 시도하는 것을
            # 막을 수 있다.
            if not force_refresh and self._is_cached_token_valid():
                assert self._cached_token is not None
                return self._cached_token

            self._cached_token = await self.issue_access_token()
            return self._cached_token

    def _is_cached_token_valid(self) -> bool:
        if self._cached_token is None:
            return False

        expires_at = self._parse_expires_dt(self._cached_token.expires_dt)
        now = datetime.now(_KST)

        return now + TOKEN_REFRESH_MARGIN < expires_at

    @staticmethod
    def _parse_expires_dt(expires_dt: str) -> datetime:
        # timezone 정책은 모듈 상단 주석 참고 — KST로 명시적으로 해석한다.
        return datetime.strptime(expires_dt, "%Y%m%d%H%M%S").replace(tzinfo=_KST)

    async def issue_access_token(self) -> KiwoomAccessToken:
        url = f"{self.base_url}/oauth2/token"

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()

        return_code = data.get("return_code")

        if return_code != 0:
            return_msg = data.get(
                "return_msg",
                "Unknown Kiwoom API error",
            )
            raise ValueError(
                f"Kiwoom API error: "
                f"return_code={return_code}, "
                f"return_msg={return_msg}"
            )

        token = data.get("token")
        token_type = data.get("token_type")
        expires_dt = data.get("expires_dt")

        if not all(
            isinstance(value, str)
            for value in (token, token_type, expires_dt)
        ):
            raise TypeError(
                f"Unexpected Kiwoom token response: {data}"
            )

        return KiwoomAccessToken(
            expires_dt=expires_dt,
            token_type=token_type,
            token=token,
        )

    async def request(
        self,
        *,
        access_token: str,
        api_id: str,
        endpoint: str,
        payload: dict[str, Any],
        cont_yn: str = "N",
        next_key: str = "",
    ) -> KiwoomApiResponse:
        url = f"{self.base_url}{endpoint}"

        headers = {
            "authorization": f"Bearer {access_token}",
            "api-id": api_id,
            "content-type": "application/json;charset=UTF-8",
            "cont-yn": cont_yn,
            "next-key": next_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()

        return_code = data.get("return_code")

        if return_code != 0:
            return_msg = data.get(
                "return_msg",
                "Unknown Kiwoom API error",
            )
            raise ValueError(
                f"Kiwoom API error: "
                f"return_code={return_code}, "
                f"return_msg={return_msg}"
            )

        return KiwoomApiResponse(
            data=data,
            cont_yn=response.headers.get("cont-yn"),
            next_key=response.headers.get("next-key"),
        )

    async def get_stock_info(
        self,
        access_token: str,
        stock_code: str,
    ) -> KiwoomStockInfo:
        retrieval = await self.fetch_stock_info(
            access_token=access_token,
            stock_code=stock_code,
        )
        return retrieval.stock_info

    async def fetch_stock_info(
        self,
        access_token: str,
        stock_code: str,
    ) -> KiwoomStockInfoRetrieval:
        response = await self.request(
            access_token=access_token,
            api_id="ka10001",
            endpoint="/api/dostk/stkinfo",
            payload={
                "stk_cd": stock_code,
            },
        )

        # 성공 응답(return_code 0) 수신 직후의 runtime retrieval 시각.
        retrieved_at = datetime.now(UTC)
        data = response.data

        stock_info = KiwoomStockInfo(
            stock_code=str(data["stk_cd"]),
            stock_name=str(data["stk_nm"]),
            current_price=self._parse_abs_int(data["cur_prc"]),
            change=self._parse_int(data["pred_pre"]),
            change_rate=self._parse_float(data["flu_rt"]),
            trading_volume=self._parse_int(data["trde_qty"]),
            per=self._parse_optional_float(data.get("per")),
            pbr=self._parse_optional_float(data.get("pbr")),
            roe=self._parse_optional_float(data.get("roe")),
            eps=self._parse_optional_int(data.get("eps")),
            bps=self._parse_optional_int(data.get("bps")),
            high_250d=self._parse_optional_abs_int(data.get("250hgst")),
            low_250d=self._parse_optional_abs_int(data.get("250lwst")),
        )

        return KiwoomStockInfoRetrieval(stock_info=stock_info, retrieved_at=retrieved_at)

    async def get_account_balance(
        self,
        access_token: str,
        query_type: str = "1",
        exchange_type: str = "KRX",
    ) -> KiwoomAccountBalance:
        payload = {
            "qry_tp": query_type,
            "dmst_stex_tp": exchange_type,
        }

        response = await self.request(
            access_token=access_token,
            api_id="kt00018",
            endpoint="/api/dostk/acnt",
            payload=payload,
        )

        data = response.data

        positions = self._parse_account_positions(
            data.get("acnt_evlt_remn_indv_tot", [])
        )

        while response.cont_yn == "Y" and response.next_key:
            response = await self.request(
                access_token=access_token,
                api_id="kt00018",
                endpoint="/api/dostk/acnt",
                payload=payload,
                cont_yn="Y",
                next_key=response.next_key,
            )

            positions.extend(
                self._parse_account_positions(
                    response.data.get(
                        "acnt_evlt_remn_indv_tot",
                        [],
                    )
                )
            )

        return KiwoomAccountBalance(
            total_purchase_amount=self._parse_int(
                data.get("tot_pur_amt", "0")
            ),
            total_evaluation_amount=self._parse_int(
                data.get("tot_evlt_amt", "0")
            ),
            total_profit_loss=self._parse_int(
                data.get("tot_evlt_pl", "0")
            ),
            total_return_rate=self._parse_float(
                data.get("tot_prft_rt", "0")
            ),
            estimated_asset_amount=self._parse_optional_int(
                data.get("prsm_dpst_aset_amt")
            ),
            total_loan_amount=self._parse_optional_int(
                data.get("tot_loan_amt")
            ),
            total_credit_loan_amount=self._parse_optional_int(
                data.get("tot_crd_loan_amt")
            ),
            total_credit_short_amount=self._parse_optional_int(
                data.get("tot_crd_ls_amt")
            ),
            positions=positions,
        )

    async def get_stock_list(
        self,
        access_token: str,
        market_code: str,
    ) -> list[KiwoomStockListItem]:
        # ka10099 종목정보 리스트. mrkt_tp는 실제 API 호출로 검증된 값만
        # 쓴다(0=코스피, 10=코스닥) — KiwoomTools가 이 raw 코드를 감춘다.
        payload = {"mrkt_tp": market_code}

        response = await self.request(
            access_token=access_token,
            api_id="ka10099",
            endpoint="/api/dostk/stkinfo",
            payload=payload,
        )

        items = self._parse_stock_list_items(response.data.get("list", []))

        # 실제 KOSPI 조회(2,481종목)에서는 페이지네이션이 발생하지 않았지만
        # (cont_yn=N), 더 큰 시장이나 향후 응답 규모 변화에 대비해 계좌잔고와
        # 동일한 연속조회 처리를 방어적으로 둔다.
        while response.cont_yn == "Y" and response.next_key:
            response = await self.request(
                access_token=access_token,
                api_id="ka10099",
                endpoint="/api/dostk/stkinfo",
                payload=payload,
                cont_yn="Y",
                next_key=response.next_key,
            )
            items.extend(self._parse_stock_list_items(response.data.get("list", [])))

        return items

    @classmethod
    def _parse_stock_list_items(
        cls,
        rows: object,
    ) -> list[KiwoomStockListItem]:
        if not isinstance(rows, list):
            raise TypeError("Unexpected Kiwoom stock list response")

        items: list[KiwoomStockListItem] = []

        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("Unexpected Kiwoom stock list item")

            items.append(
                KiwoomStockListItem(
                    symbol=str(row.get("code", "")),
                    name=str(row.get("name", "")),
                    market_name=str(row.get("marketName", "")),
                    sector_name=str(row.get("upName", "")),
                    size_name=str(row.get("upSizeName", "")),
                    listed_shares=cls._parse_int(row.get("listCount", "0")),
                    last_price=cls._parse_int(row.get("lastPrice", "0")),
                    audit_info=str(row.get("auditInfo", "")),
                    order_warning=str(row.get("orderWarning", "")),
                )
            )

        return items

    async def get_theme_groups(
        self,
        access_token: str,
        *,
        force_refresh: bool = False,
    ) -> list[KiwoomThemeGroup]:
        """ka90001 테마그룹별요청(qry_tp=전체검색)으로 전체 테마 카탈로그를
        조회한다. THEME_CATALOG_CACHE_TTL 동안 instance-level로 캐시한다 —
        UX-01 Candidate Discovery가 매 요청마다 142개 테마 전체를 다시
        조회하지 않도록 하기 위함이다(모듈 상단 주석 참고)."""
        if not force_refresh and self._is_theme_catalog_cache_valid():
            assert self._theme_catalog_cache is not None
            return self._theme_catalog_cache

        groups = await self._fetch_theme_groups(access_token)

        self._theme_catalog_cache = groups
        self._theme_catalog_cached_at = datetime.now(_KST)
        return groups

    def _is_theme_catalog_cache_valid(self) -> bool:
        if self._theme_catalog_cache is None or self._theme_catalog_cached_at is None:
            return False

        return datetime.now(_KST) - self._theme_catalog_cached_at < THEME_CATALOG_CACHE_TTL

    async def _fetch_theme_groups(self, access_token: str) -> list[KiwoomThemeGroup]:
        payload = {
            "qry_tp": _THEME_GROUP_QUERY_ALL,
            "date_tp": _THEME_GROUP_DATE_TP,
            "flu_pl_amt_tp": _THEME_GROUP_FLU_PL_AMT_TP,
            "stex_tp": _THEME_GROUP_STEX_TP,
            "stk_cd": "",
            "thema_nm": "",
        }

        response = await self.request(
            access_token=access_token,
            api_id="ka90001",
            endpoint="/api/dostk/thme",
            payload=payload,
        )

        groups = self._parse_theme_groups(response.data.get("thema_grp", []))

        while response.cont_yn == "Y" and response.next_key:
            response = await self.request(
                access_token=access_token,
                api_id="ka90001",
                endpoint="/api/dostk/thme",
                payload=payload,
                cont_yn="Y",
                next_key=response.next_key,
            )
            groups.extend(self._parse_theme_groups(response.data.get("thema_grp", [])))

        return groups

    @classmethod
    def _parse_theme_groups(
        cls,
        rows: object,
    ) -> list[KiwoomThemeGroup]:
        if not isinstance(rows, list):
            raise TypeError("Unexpected Kiwoom theme group response")

        groups: list[KiwoomThemeGroup] = []

        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("Unexpected Kiwoom theme group item")

            groups.append(
                KiwoomThemeGroup(
                    theme_code=str(row.get("thema_grp_cd", "")),
                    theme_name=str(row.get("thema_nm", "")),
                    stock_count=cls._parse_int(row.get("stk_num", "0")),
                )
            )

        return groups

    async def get_theme_stocks(
        self,
        access_token: str,
        theme_code: str,
    ) -> list[KiwoomThemeStock]:
        # ka90002 테마구성종목요청. Theme catalog와 달리 멤버십 자체는
        # 캐시하지 않는다(UX-01 v1은 요청된 테마만 그때그때 lazy하게
        # 조회한다 — 142개 테마 전체 멤버십을 미리 구축하지 않는다).
        payload = {
            "thema_grp_cd": theme_code,
            "stex_tp": _THEME_STOCK_STEX_TP,
            "date_tp": _THEME_STOCK_DATE_TP,
        }

        response = await self.request(
            access_token=access_token,
            api_id="ka90002",
            endpoint="/api/dostk/thme",
            payload=payload,
        )

        stocks = self._parse_theme_stocks(response.data.get("thema_comp_stk", []))

        while response.cont_yn == "Y" and response.next_key:
            response = await self.request(
                access_token=access_token,
                api_id="ka90002",
                endpoint="/api/dostk/thme",
                payload=payload,
                cont_yn="Y",
                next_key=response.next_key,
            )
            stocks.extend(self._parse_theme_stocks(response.data.get("thema_comp_stk", [])))

        return stocks

    @classmethod
    def _parse_theme_stocks(
        cls,
        rows: object,
    ) -> list[KiwoomThemeStock]:
        if not isinstance(rows, list):
            raise TypeError("Unexpected Kiwoom theme stock response")

        stocks: list[KiwoomThemeStock] = []

        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("Unexpected Kiwoom theme stock item")

            stocks.append(
                KiwoomThemeStock(
                    stock_code=str(row.get("stk_cd", "")),
                    stock_name=str(row.get("stk_nm", "")),
                )
            )

        return stocks

    def _parse_account_positions(
        self,
        rows: object,
    ) -> list[KiwoomAccountPosition]:
        if not isinstance(rows, list):
            raise TypeError(
                "Unexpected Kiwoom account position response"
            )

        positions: list[KiwoomAccountPosition] = []

        for row in rows:
            if not isinstance(row, dict):
                raise TypeError(
                    "Unexpected Kiwoom account position item"
                )

            positions.append(
                KiwoomAccountPosition(
                    stock_code=self._normalize_stock_code(str(row.get("stk_cd", ""))),
                    stock_name=str(row.get("stk_nm", "")),
                    quantity=self._parse_int(
                        row.get("rmnd_qty", "0")
                    ),
                    tradable_quantity=self._parse_int(
                        row.get("trde_able_qty", "0")
                    ),
                    average_price=self._parse_abs_int(
                        row.get("pur_pric", "0")
                    ),
                    current_price=self._parse_abs_int(
                        row.get("cur_prc", "0")
                    ),
                    purchase_amount=self._parse_int(
                        row.get("pur_amt", "0")
                    ),
                    evaluation_amount=self._parse_int(
                        row.get("evlt_amt", "0")
                    ),
                    profit_loss=self._parse_int(
                        row.get("evltv_prft", "0")
                    ),
                    return_rate=self._parse_float(
                        row.get("prft_rt", "0")
                    ),
                    portfolio_weight=self._parse_float(
                        row.get("poss_rt", "0")
                    ),
                )
            )

        return positions

    @staticmethod
    def _normalize_stock_code(code: str) -> str:
        # 계좌평가잔고(kt00018) 응답의 stk_cd는 실제로 시장 구분 접두문자가
        # 붙은 채로 내려온다(예: "A005930"). 주식기본정보 조회(get_stock_info)
        # 등 다른 Kiwoom API는 접두문자 없는 순수 종목코드("005930")를
        # 기대하므로, Service 계층에서 정규화해 시스템 전체가 항상 일관된
        # 종목코드를 쓰도록 한다.
        if len(code) == 7 and code[0].isalpha() and code[1:].isdigit():
            return code[1:]

        return code

    @staticmethod
    def _parse_int(value: object) -> int:
        return int(str(value).replace(",", ""))

    @staticmethod
    def _parse_float(value: object) -> float:
        return float(str(value).replace(",", ""))

    @classmethod
    def _parse_abs_int(cls, value: object) -> int:
        return abs(cls._parse_int(value))

    @classmethod
    def _parse_optional_int(
        cls,
        value: object,
    ) -> int | None:
        if value is None or value == "":
            return None

        return cls._parse_int(value)

    @classmethod
    def _parse_optional_abs_int(
        cls,
        value: object,
    ) -> int | None:
        parsed = cls._parse_optional_int(value)

        if parsed is None:
            return None

        return abs(parsed)

    @classmethod
    def _parse_optional_float(
        cls,
        value: object,
    ) -> float | None:
        if value is None or value == "":
            return None

        return cls._parse_float(value)