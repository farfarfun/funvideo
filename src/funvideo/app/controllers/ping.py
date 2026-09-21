from fastapi import APIRouter, Request

router = APIRouter()


@router.get(
    "/ping",
    tags=["Health Check"],
    description="检查服务可用性",
    response_description="pong",
)
def ping(request: Request) -> str:
    """返回服务健康状态。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        固定字符串 ``pong``。
    """
    return "pong"
