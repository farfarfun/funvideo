import glob
import os
import pathlib
import shutil
from collections.abc import Iterator
from typing import Any

from farlog import getLogger
from fastapi import BackgroundTasks, Depends, Path, Request, UploadFile
from fastapi.params import File
from fastapi.responses import FileResponse, StreamingResponse

from funvideo.app.config import config
from funvideo.app.controllers import base
from funvideo.app.controllers.manager.memory_manager import InMemoryTaskManager
from funvideo.app.controllers.manager.redis_manager import RedisTaskManager
from funvideo.app.controllers.v1.base import new_router
from funvideo.app.models.exception import HttpException
from funvideo.app.models.schema import (
    AudioRequest,
    BgmRetrieveResponse,
    BgmUploadResponse,
    SubtitleRequest,
    TaskDeletionResponse,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskResponse,
    TaskVideoRequest,
)
from funvideo.app.services import state as sm
from funvideo.app.services import task as tm
from funvideo.app.utils import utils

logger = getLogger("funvideo")
# 认证依赖项
# router = new_router(dependencies=[Depends(base.verify_token)])
router = new_router()

_enable_redis = config.app.get("enable_redis", False)
_redis_host = config.app.get("redis_host", "localhost")
_redis_port = config.app.get("redis_port", 6379)
_redis_db = config.app.get("redis_db", 0)
_redis_password = config.get_secret("app", "redis_password")
_max_concurrent_tasks = config.app.get("max_concurrent_tasks", 5)

redis_url = f"redis://:{_redis_password}@{_redis_host}:{_redis_port}/{_redis_db}"
# 根据配置选择合适的任务管理器
if _enable_redis:
    task_manager = RedisTaskManager(
        max_concurrent_tasks=_max_concurrent_tasks, redis_url=redis_url
    )
else:
    task_manager = InMemoryTaskManager(max_concurrent_tasks=_max_concurrent_tasks)


@router.post("/videos", response_model=TaskResponse, summary="Generate a short video")
def create_video(
    background_tasks: BackgroundTasks, request: Request, body: TaskVideoRequest
) -> dict[str, Any]:
    """创建完整视频生成任务。

    Args:
        background_tasks: FastAPI 后台任务容器。
        request: 当前请求。
        body: 视频生成参数。

    Returns:
        包含任务 ID 的标准响应字典。
    """
    return create_task(request, body, stop_at="video")


@router.post("/subtitle", response_model=TaskResponse, summary="Generate subtitle only")
def create_subtitle(
    background_tasks: BackgroundTasks, request: Request, body: SubtitleRequest
) -> dict[str, Any]:
    """创建仅生成字幕的任务。

    Args:
        background_tasks: FastAPI 后台任务容器。
        request: 当前请求。
        body: 字幕和语音参数。

    Returns:
        包含任务 ID 的标准响应字典。
    """
    return create_task(request, body, stop_at="subtitle")


@router.post("/audio", response_model=TaskResponse, summary="Generate audio only")
def create_audio(
    background_tasks: BackgroundTasks, request: Request, body: AudioRequest
) -> dict[str, Any]:
    """创建仅生成音频的任务。

    Args:
        background_tasks: FastAPI 后台任务容器。
        request: 当前请求。
        body: 音频生成参数。

    Returns:
        包含任务 ID 的标准响应字典。
    """
    return create_task(request, body, stop_at="audio")


def create_task(
    request: Request,
    body: TaskVideoRequest | SubtitleRequest | AudioRequest,
    stop_at: str,
) -> dict[str, Any]:
    """登记生成任务并交给任务管理器执行。

    Args:
        request: 当前请求。
        body: 视频、字幕或音频参数。
        stop_at: 流水线停止阶段。

    Returns:
        包含任务 ID 的标准响应字典。
    """
    task_id = utils.get_uuid()
    request_id = base.get_task_id(request)
    try:
        task = {
            "task_id": task_id,
            "request_id": request_id,
            "params": body.model_dump(),
        }
        sm.state.update_task(task_id)
        task_manager.add_task(tm.start, task_id=task_id, params=body, stop_at=stop_at)
        logger.success(f"Task created: {utils.to_json(task)}")
        return utils.get_response(200, task)
    except ValueError as e:
        raise HttpException(
            task_id=task_id, status_code=400, message=f"{request_id}: {str(e)}"
        )


@router.get(
    "/tasks/{task_id}", response_model=TaskQueryResponse, summary="Query task status"
)
def get_task(
    request: Request,
    task_id: str = Path(..., description="Task ID"),
    query: TaskQueryRequest = Depends(),
) -> dict[str, Any]:
    """查询任务状态和产物地址。

    Args:
        request: 当前请求，用于生成产物 URL。
        task_id: 待查询的任务 ID。
        query: 查询参数对象。

    Returns:
        任务状态和产物信息。
    """
    endpoint = config.app.get("endpoint", "")
    if not endpoint:
        endpoint = str(request.base_url)
    endpoint = endpoint.rstrip("/")

    request_id = base.get_task_id(request)
    task = sm.state.get_task(task_id)
    if task:
        task_dir = utils.task_dir()

        def file_to_uri(file: str) -> str:
            if not file.startswith(endpoint):
                _uri_path = file.replace(task_dir, "tasks").replace("\\", "/")
                _uri_path = f"{endpoint}/{_uri_path}"
            else:
                _uri_path = file
            return _uri_path

        if "videos" in task:
            videos = task["videos"]
            urls = []
            for v in videos:
                urls.append(file_to_uri(v))
            task["videos"] = urls
        if "combined_videos" in task:
            combined_videos = task["combined_videos"]
            urls = []
            for v in combined_videos:
                urls.append(file_to_uri(v))
            task["combined_videos"] = urls
        return utils.get_response(200, task)

    raise HttpException(
        task_id=task_id, status_code=404, message=f"{request_id}: task not found"
    )


@router.delete(
    "/tasks/{task_id}",
    response_model=TaskDeletionResponse,
    summary="Delete a generated short video task",
)
def delete_video(
    request: Request, task_id: str = Path(..., description="Task ID")
) -> dict[str, Any]:
    """删除任务状态和本地产物目录。

    Args:
        request: 当前请求。
        task_id: 待删除的任务 ID。

    Returns:
        标准成功响应字典。
    """
    request_id = base.get_task_id(request)
    task = sm.state.get_task(task_id)
    if task:
        tasks_dir = utils.task_dir()
        current_task_dir = os.path.join(tasks_dir, task_id)
        if os.path.exists(current_task_dir):
            shutil.rmtree(current_task_dir)

        sm.state.delete_task(task_id)
        logger.success(f"video deleted: {utils.to_json(task)}")
        return utils.get_response(200)

    raise HttpException(
        task_id=task_id, status_code=404, message=f"{request_id}: task not found"
    )


@router.get(
    "/musics", response_model=BgmRetrieveResponse, summary="Retrieve local BGM files"
)
def get_bgm_list(request: Request) -> dict[str, Any]:
    """返回本地可用的 MP3 背景音乐列表。

    Args:
        request: 当前请求。

    Returns:
        包含文件名、大小和路径的标准响应字典。
    """
    suffix = "*.mp3"
    song_dir = utils.song_dir()
    files = glob.glob(os.path.join(song_dir, suffix))
    bgm_list = []
    for file in files:
        bgm_list.append(
            {
                "name": os.path.basename(file),
                "size": os.path.getsize(file),
                "file": file,
            }
        )
    response = {"files": bgm_list}
    return utils.get_response(200, response)


@router.post(
    "/musics",
    response_model=BgmUploadResponse,
    summary="Upload the BGM file to the songs directory",
)
def upload_bgm_file(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """上传 MP3 背景音乐。

    Args:
        request: 当前请求。
        file: 待上传的 MP3 文件。

    Returns:
        保存后的文件路径。
    """
    request_id = base.get_task_id(request)
    filename = pathlib.Path(file.filename or "").name
    if pathlib.Path(filename).suffix.lower() == ".mp3":
        song_dir = utils.song_dir()
        save_path = os.path.join(song_dir, filename)
        # save file
        with open(save_path, "wb+") as buffer:
            # If the file already exists, it will be overwritten
            file.file.seek(0)
            buffer.write(file.file.read())
        response = {"file": save_path}
        return utils.get_response(200, response)

    raise HttpException(
        "", status_code=400, message=f"{request_id}: Only *.mp3 files can be uploaded"
    )


@router.get("/stream/{file_path:path}")
async def stream_video(request: Request, file_path: str) -> StreamingResponse:
    """按 HTTP Range 流式返回任务视频。

    Args:
        request: 当前请求，可能包含 Range 头。
        file_path: 相对于任务目录的视频路径。

    Returns:
        支持分段读取的视频响应。
    """
    video_path = _resolve_task_file(file_path)
    range_header = request.headers.get("Range")
    video_size = os.path.getsize(video_path)
    start, end = 0, video_size - 1

    length = video_size
    if range_header:
        range_ = range_header.split("bytes=")[1]
        start, end = [int(part) if part else None for part in range_.split("-")]
        if start is None:
            start = video_size - end
            end = video_size - 1
        if end is None:
            end = video_size - 1
        length = end - start + 1

    def file_iterator(
        file_path: pathlib.Path, offset: int = 0, bytes_to_read: int | None = None
    ) -> Iterator[bytes]:
        with open(file_path, "rb") as f:
            f.seek(offset, os.SEEK_SET)
            remaining = bytes_to_read or video_size
            while remaining > 0:
                bytes_to_read = min(4096, remaining)
                data = f.read(bytes_to_read)
                if not data:
                    break
                remaining -= len(data)
                yield data

    response = StreamingResponse(
        file_iterator(video_path, start, length), media_type="video/mp4"
    )
    response.headers["Content-Range"] = f"bytes {start}-{end}/{video_size}"
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = str(length)
    response.status_code = 206  # Partial Content

    return response


@router.get("/download/{file_path:path}")
async def download_video(_: Request, file_path: str) -> FileResponse:
    """下载任务视频。

    Args:
        _: 当前请求。
        file_path: 相对于任务目录的视频路径。

    Returns:
        视频文件下载响应。
    """
    video_path = _resolve_task_file(file_path)
    file_path = video_path
    filename = file_path.stem
    extension = file_path.suffix
    headers = {"Content-Disposition": f"attachment; filename={filename}{extension}"}
    return FileResponse(
        path=video_path,
        headers=headers,
        filename=f"{filename}{extension}",
        media_type=f"video/{extension[1:]}",
    )


def _resolve_task_file(file_path: str) -> pathlib.Path:
    """解析任务文件路径，并拒绝目录穿越和不存在的文件。"""
    tasks_dir = pathlib.Path(utils.task_dir()).resolve()
    target = (tasks_dir / file_path).resolve()
    if not target.is_relative_to(tasks_dir) or not target.is_file():
        raise HttpException("", status_code=404, message="video file not found")
    return target
