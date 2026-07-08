import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deliveries import router as deliveries_router

# uvicorn 은 앱 로거에 핸들러를 안 붙여 INFO 가 묻힌다. app.* 로거를 콘솔로 노출.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("INFO:     [app] %(message)s"))
    _app_logger.addHandler(_handler)
    _app_logger.setLevel(logging.INFO)
    _app_logger.propagate = False

app = FastAPI(title="PinkyCare Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # localhost 개발 + 같은 Wi-Fi 의 사설망 IP(태블릿/폰에서 접속) 모두 허용
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_DEFAULT_CODES = {
    404: "NOT_FOUND",
    409: "INVALID_TRANSITION",
    422: "VALIDATION_ERROR",
}


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{loc}: {first.get('msg', 'invalid')}" if loc else first.get("msg", "invalid")
    else:
        message = "Validation failed"
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        payload = {"code": detail["code"], "message": detail.get("message", "")}
    else:
        payload = {
            "code": _DEFAULT_CODES.get(exc.status_code, "INTERNAL_ERROR"),
            "message": str(detail),
        }
    return JSONResponse(status_code=exc.status_code, content={"error": payload})


app.include_router(deliveries_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
