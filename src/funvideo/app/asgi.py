"""Application implementation - ASGI."""

import os

from farlog import getLogger
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from funvideo.app.config import config
from funvideo.app.models.exception import HttpException
from funvideo.app.router import root_api_router
from funvideo.app.utils import utils

logger = getLogger("funvideo")


def exception_handler(request: Request, e: HttpException) -> JSONResponse:
    """将业务异常转换为统一 JSON 响应。"""
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(
    request: Request, e: RequestValidationError
) -> JSONResponse:
    """将请求校验异常转换为 400 JSON 响应。"""
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """构建并返回已注册路由和异常处理器的 FastAPI 应用。"""
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

def _cors_settings(value: str | None) -> tuple[list[str], bool]:
    """解析显式 CORS 来源，并返回来源列表和是否允许携带凭据。"""
    origins = [origin.strip() for origin in (value or "").split(",") if origin.strip()]
    return origins, bool(origins) and "*" not in origins


origins, allow_credentials = _cors_settings(os.getenv("CORS_ALLOWED_ORIGINS"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()
app.mount(
    "/tasks", StaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="")


@app.on_event("shutdown")
def shutdown_event() -> None:
    """记录应用关闭事件。"""
    logger.info("shutdown event")


@app.on_event("startup")
def startup_event() -> None:
    """记录应用启动事件。"""
    logger.info("startup event")
