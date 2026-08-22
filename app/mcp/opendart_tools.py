from pydantic import BaseModel

from app.services.opendart import OpenDartFinancialAccount, OpenDartService


class CompanyFinancials(BaseModel):
    stock_code: str
    corp_code: str
    business_year: str
    report_code: str
    accounts: list[OpenDartFinancialAccount]


class KeyFinancials(BaseModel):
    stock_code: str
    corp_code: str
    business_year: str
    report_code: str
    fs_div: str
    revenue: int | None
    operating_profit: int | None
    net_income: int | None
    total_assets: int | None
    total_liabilities: int | None
    total_equity: int | None


class OpenDartTools:
    def __init__(self, service: OpenDartService) -> None:
        self.service = service

    async def get_company_financials(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> CompanyFinancials:
        corp_code = await self.service.resolve_corp_code(stock_code)

        accounts = await self.service.get_financial_accounts(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )

        return CompanyFinancials(
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            accounts=accounts,
        )

    async def get_key_financials(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> KeyFinancials:
        financials = await self.get_company_financials(
            stock_code=stock_code,
            business_year=business_year,
            report_code=report_code,
        )

        accounts = financials.accounts

        if any(account.fs_div == "CFS" for account in accounts):
            fs_div = "CFS"
        else:
            fs_div = "OFS"

        selected_accounts = [
            account
            for account in accounts
            if account.fs_div == fs_div
        ]

        return KeyFinancials(
            stock_code=financials.stock_code,
            corp_code=financials.corp_code,
            business_year=financials.business_year,
            report_code=financials.report_code,
            fs_div=fs_div,
            revenue=self._find_amount(
                selected_accounts,
                {"매출액"},
            ),
            operating_profit=self._find_amount(
                selected_accounts,
                {"영업이익"},
            ),
            net_income=self._find_amount(
                selected_accounts,
                {
                    "당기순이익",
                    "당기순이익(손실)",
                },
            ),
            total_assets=self._find_amount(
                selected_accounts,
                {"자산총계"},
            ),
            total_liabilities=self._find_amount(
                selected_accounts,
                {"부채총계"},
            ),
            total_equity=self._find_amount(
                selected_accounts,
                {"자본총계"},
            ),
        )

    @staticmethod
    def _find_amount(
        accounts: list[OpenDartFinancialAccount],
        account_names: set[str],
    ) -> int | None:
        for account in accounts:
            if account.account_name in account_names:
                return account.current_term_amount

        return None