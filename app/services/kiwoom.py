from typing import Any

import httpx
from pydantic import BaseModel


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
                    stock_code=str(row.get("stk_cd", "")),
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