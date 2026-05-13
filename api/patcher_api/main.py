from fastapi import FastAPI

from patcher_api.routes import apps

app = FastAPI(
    title="Patcher API",
    description="Community catalog of macOS app patching metadata.",
    version="0.1.0",
)

app.include_router(apps.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
