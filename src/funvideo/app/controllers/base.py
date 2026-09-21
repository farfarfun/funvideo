from uuid import uuid4

from fastapi import Request

from funvideo.app.config import config
from funvideo.app.models.exception import HttpException


def get_task_id(request: Request) -> str:
    """返回请求头中的任务 ID；未提供时生成新 ID。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        可用于日志和任务追踪的字符串 ID。
    """
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request) -> str | None:
    """读取请求携带的 API 密钥。"""
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request) -> None:
    """校验请求 API 密钥，不匹配时抛出 401 异常。"""
    token = get_api_key(request)
    if token != config.get_secret("app", "api_key", ""):
        request_id = get_task_id(request)
        request_url = request.url
        user_agent = request.headers.get("user-agent")
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message=f"invalid token: {request_url}, {user_agent}",
        )
