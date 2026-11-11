from contextlib import asynccontextmanager

from fastapi import FastAPI

from .init_opensearch import init_all
from .routers import auth, logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_all(force_drop_logs=False)
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(logs.router)
app.include_router(auth.router)

@app.get("/health")
def health():
    return {
        "status": "OK",
        "service": "Log-Assistant Backend API",
    }