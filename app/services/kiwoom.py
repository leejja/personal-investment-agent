import asyncio
from datetime import datetime, timedelta
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
        response = await self.request(
            access_token=access_token,
            api_id="ka10001",
            endpoint="/api/dostk/stkinfo",
            payload={
                "stk_cd": stock_code,
            },
        )

        data = response.data

        return KiwoomStockInfo(
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