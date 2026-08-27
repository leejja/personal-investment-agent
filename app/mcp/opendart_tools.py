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

    async def find_stock_code_by_name(self, company_name: str) -> str | None:
        # Supervisor가 사용자 발화에 등장한 회사명(예: "삼성전자")을 종목코드로
        # 정확히 일치하는 경우에만 해석하기 위한 조회다. LLM이 종목코드를
        # 스스로 만들어내지 않도록, 코드 매핑은 항상 이 결정론적 조회를
        # 거친다. 정확히 하나로 특정되지 않으면(없거나 모호하면) None을
        # 반환해 호출자가 추측 없이 실패 처리하게 한다.
        corporations = await self.service.get_corporations()

        matches = [
            corporation
            for corporation in corporations
            if corporation.stock_code is not None
            and corporation.corp_name == company_name
        ]

        if len(matches) != 1:
            return None

        return matches[0].stock_code

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
        fs_div = self._select_fs_div(accounts)
        selected_accounts = [
            account for account in accounts if account.fs_div == fs_div
        ]

        return self._extract_key_financials(
            selected_accounts,
            stock_code=financials.stock_code,
            corp_code=financials.corp_code,
            business_year=financials.business_year,
            report_code=financials.report_code,
            fs_div=fs_div,
            term="current",
        )

    async def get_key_financials_history(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> list[KeyFinancials]:
        # 항상 최소 1건(당기)은 포함한다 — get_key_financials()와 동일한
        # 보장. OpenDART fnlttSinglAcnt.json은 사업보고서(11011)일 때만
        # 전기(frmtrm)/전전기(bfefrmtrm) 컬럼까지 함께 내려주는 것으로 실제
        # API 호출로 확인했다. 분기/반기 보고서와 섞여 잘못된 추세로
        # 해석되지 않도록, 사업보고서가 아니면 당기 1건만 반환한다.
        #
        # 이 메서드는 get_key_financials()를 호출하지 않고 get_company_financials()를
        # 직접 한 번만 호출한다 — 두 메서드를 함께 쓸 때 OpenDART API를 두 번
        # 부르지 않기 위함이다(추가 API 호출 없음).
        financials = await self.get_company_financials(
            stock_code=stock_code,
            business_year=business_year,
            report_code=report_code,
        )

        accounts = financials.accounts
        fs_div = self._select_fs_div(accounts)
        selected_accounts = [
            account for account in accounts if account.fs_div == fs_div
        ]

        terms = ["current"]
        if report_code == "11011":
            terms += ["previous", "before_previous"]

        history: list[KeyFinancials] = []
        for term in terms:
            key_financials = self._extract_key_financials(
                selected_accounts,
                stock_code=financials.stock_code,
                corp_code=financials.corp_code,
                business_year=_year_label_for_term(business_year, term),
                report_code=report_code,
                fs_div=fs_div,
                term=term,
            )

            # 당기는 항상 포함한다(값이 전부 비어 있더라도 기존
            # get_key_financials()와 동일한 동작을 보장). 전기/전전기는
            # 값이 전부 None이면(상장 이력이 짧은 회사 등) 의미 있는
            # 데이터가 없다는 뜻이므로 결과에서 생략한다.
            if term == "current" or self._has_any_value(key_financials):
                history.append(key_financials)

        return history

    @staticmethod
    def _select_fs_div(accounts: list[OpenDartFinancialAccount]) -> str:
        if any(account.fs_div == "CFS" for account in accounts):
            return "CFS"
        return "OFS"

    @classmethod
    def _extract_key_financials(
        cls,
        accounts: list[OpenDartFinancialAccount],
        *,
        stock_code: str,
        corp_code: str,
        business_year: str,
        report_code: str,
        fs_div: str,
        term: str,
    ) -> KeyFinancials:
        return KeyFinancials(
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            fs_div=fs_div,
            revenue=cls._find_amount(accounts, {"매출액"}, term),
            operating_profit=cls._find_amount(accounts, {"영업이익"}, term),
            net_income=cls._find_amount(
                accounts,
                {"당기순이익", "당기순이익(손실)"},
                term,
            ),
            total_assets=cls._find_amount(accounts, {"자산총계"}, term),
            total_liabilities=cls._find_amount(accounts, {"부채총계"}, term),
            total_equity=cls._find_amount(accounts, {"자본총계"}, term),
        )

    @staticmethod
    def _has_any_value(key_financials: KeyFinancials) -> bool:
        return any(
            value is not None
            for value in (
                key_financials.revenue,
                key_financials.operating_profit,
                key_financials.net_income,
                key_financials.total_assets,
                key_financials.total_liabilities,
                key_financials.total_equity,
            )
        )

    @staticmethod
    def _find_amount(
        accounts: list[OpenDartFinancialAccount],
        account_names: set[str],
        term: str = "current",
    ) -> int | None:
        amount_attr = {
            "current": "current_term_amount",
            "previous": "previous_term_amount",
            "before_previous": "before_previous_term_amount",
        }[term]

        for account in accounts:
            if account.account_name in account_names:
                return getattr(account, amount_attr)

        return None


def _year_label_for_term(business_year: str, term: str) -> str:
    offset = {"current": 0, "previous": 1, "before_previous": 2}[term]
    return str(int(business_year) - offset)