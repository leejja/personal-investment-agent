import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import httpx
from pydantic import BaseModel


class OpenDartCorporation(BaseModel):
    corp_code: str
    corp_name: str
    corp_eng_name: str | None
    stock_code: str | None
    modify_date: str


class OpenDartFinancialAccount(BaseModel):
    rcept_no: str
    bsns_year: str
    stock_code: str
    reprt_code: str
    account_name: str
    fs_div: str
    fs_name: str
    statement_div: str
    statement_name: str
    current_term_name: str
    current_term_date: str
    current_term_amount: int | None
    previous_term_name: str
    previous_term_date: str
    previous_term_amount: int | None
    currency: str


class OpenDartService:
    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def get_corporations(self) -> list[OpenDartCorporation]:
        url = f"{self.BASE_URL}/corpCode.xml"

        params = {
            "crtfc_key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        return self._parse_corporation_zip(response.content)

    async def resolve_corp_code(self, stock_code: str) -> str:
        corporations = await self.get_corporations()

        for corporation in corporations:
            if corporation.stock_code == stock_code:
                return corporation.corp_code

        raise ValueError(f"OpenDART corporation not found: {stock_code}")

    async def get_financial_accounts(
        self,
        corp_code: str,
        business_year: str,
        report_code: str,
    ) -> list[OpenDartFinancialAccount]:
        url = f"{self.BASE_URL}/fnlttSinglAcnt.json"

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": business_year,
            "reprt_code": report_code,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        data = response.json()

        status = data.get("status")

        if status != "000":
            message = data.get("message", "Unknown OpenDART error")
            raise ValueError(
                f"OpenDART API error: status={status}, message={message}"
            )

        rows = data.get("list")

        if not isinstance(rows, list):
            raise TypeError(f"Unexpected OpenDART response: {data}")

        return [self._convert_financial_account(row) for row in rows]

    def _parse_corporation_zip(
        self,
        content: bytes,
    ) -> list[OpenDartCorporation]:
        with ZipFile(BytesIO(content)) as archive:
            filenames = archive.namelist()

            if not filenames:
                raise ValueError("Empty OpenDART corporation archive")

            xml_content = archive.read(filenames[0])

        root = ET.fromstring(xml_content)

        corporations: list[OpenDartCorporation] = []

        for item in root.findall("list"):
            corp_code = item.findtext("corp_code")
            corp_name = item.findtext("corp_name")
            modify_date = item.findtext("modify_date")

            if corp_code is None or corp_name is None or modify_date is None:
                continue

            stock_code = item.findtext("stock_code")
            corp_eng_name = item.findtext("corp_eng_name")

            corporations.append(
                OpenDartCorporation(
                    corp_code=corp_code.strip(),
                    corp_name=corp_name.strip(),
                    corp_eng_name=self._normalize_optional_text(corp_eng_name),
                    stock_code=self._normalize_optional_text(stock_code),
                    modify_date=modify_date.strip(),
                )
            )

        return corporations

    def _convert_financial_account(
        self,
        row: dict[str, Any],
    ) -> OpenDartFinancialAccount:
        return OpenDartFinancialAccount(
            rcept_no=row["rcept_no"],
            bsns_year=row["bsns_year"],
            stock_code=row["stock_code"],
            reprt_code=row["reprt_code"],
            account_name=row["account_nm"],
            fs_div=row["fs_div"],
            fs_name=row["fs_nm"],
            statement_div=row["sj_div"],
            statement_name=row["sj_nm"],
            current_term_name=row["thstrm_nm"],
            current_term_date=row["thstrm_dt"],
            current_term_amount=self._parse_amount(row.get("thstrm_amount")),
            previous_term_name=row["frmtrm_nm"],
            previous_term_date=row["frmtrm_dt"],
            previous_term_amount=self._parse_amount(row.get("frmtrm_amount")),
            currency=row["currency"],
        )

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _parse_amount(value: str | None) -> int | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return int(value.replace(",", ""))