from typing import Any

from fastapi import Request

from funvideo.app.controllers.v1.base import new_router
from funvideo.app.models.exception import HttpException
from funvideo.app.models.schema import (
    VideoScriptRequest,
    VideoScriptResponse,
    VideoTermsRequest,
    VideoTermsResponse,
)
from funvideo.app.services import llm
from funvideo.app.utils import utils

# 认证依赖项
# router = new_router(dependencies=[Depends(base.verify_token)])
router = new_router()


@router.post(
    "/scripts",
    response_model=VideoScriptResponse,
    summary="Create a script for the video",
)
def generate_video_script(request: Request, body: VideoScriptRequest) -> dict[str, Any]:
    """根据视频主题生成脚本。

    Args:
        request: 当前 FastAPI 请求。
        body: 视频主题、语言和段落数量。

    Returns:
        包含生成脚本的标准响应字典。
    """
    try:
        video_script = llm.generate_script(
            video_subject=body.video_subject,
            language=body.video_language,
            paragraph_number=body.paragraph_number,
        )
    except llm.LLMGenerationError as error:
        raise HttpException("", 502, str(error)) from error
    response = {"video_script": video_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=VideoTermsResponse,
    summary="Generate video terms based on the video script",
)
def generate_video_terms(request: Request, body: VideoTermsRequest) -> dict[str, Any]:
    """根据视频脚本生成素材检索词。

    Args:
        request: 当前 FastAPI 请求。
        body: 视频主题、脚本和检索词数量。

    Returns:
        包含素材检索词的标准响应字典。
    """
    try:
        video_terms = llm.generate_terms(
            video_subject=body.video_subject,
            video_script=body.video_script,
            amount=body.amount,
        )
    except llm.LLMGenerationError as error:
        raise HttpException("", 502, str(error)) from error
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)
