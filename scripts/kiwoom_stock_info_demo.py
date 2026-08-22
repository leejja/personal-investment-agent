import asyncio

from app.config import settings
from app.services.kiwoom import KiwoomService


async def main() -> None:
    service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )

    token = await service.issue_access_token()

    result = await service.request(
        access_token=token.token,
        api_id="ka10001",
        endpoint="/api/dostk/stkinfo",
        payload={
            "stk_cd": "005930",
        },
    )

    print("=== Kiwoom Samsung Electronics Stock Info ===")

    for key, value in result.data.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())