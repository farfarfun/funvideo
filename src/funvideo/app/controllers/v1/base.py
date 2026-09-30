from collections.abc import Sequence

from fastapi import APIRouter
from fastapi.params import Depends


def new_router(dependencies: Sequence[Depends] | None = None) -> APIRouter:
    """创建带统一 V1 前缀及可选依赖项的 API 路由。"""
    router = APIRouter()
    router.tags = ["V1"]
    router.prefix = "/api/v1"
    # 将认证依赖项应用于所有路由
    if dependencies:
        router.dependencies = dependencies
    return router
