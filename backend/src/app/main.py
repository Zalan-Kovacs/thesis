from fastapi import FastAPI

from .routers import logs

app = FastAPI()

app.include_router(logs.router)

@app.get("/")
def readRoot():
    return {"Hello": "World"}


@app.get("/check")
def healthCheck():
    return {"status": "200 OK", "service": "Log-Assistant Backend API"}

    
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
