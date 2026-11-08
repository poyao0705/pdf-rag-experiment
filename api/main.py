from asgi_correlation_id import CorrelationIdMiddleware, correlation_id
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.lifespan import lifespan
from core.middleware import RequestLoggingMiddleware

app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-ID": correlation_id.get() or ""},
    )


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/")
def main():
    return {"message": "Hello World"}
