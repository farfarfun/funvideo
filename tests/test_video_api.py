from pathlib import Path

import pytest


def test_create_video_enqueues_task_without_running_pipeline(client, monkeypatch):
    """视频接口正常路径只登记任务，不在请求线程运行外部流水线。"""
    from funvideo.app.controllers.v1 import video

    queued = []
    monkeypatch.setattr(
        video.task_manager,
        "add_task",
        lambda func, *args, **kwargs: queued.append((func, args, kwargs)),
    )

    response = client.post("/api/v1/videos", json={"video_subject": "测试视频"})

    assert response.status_code == 200
    assert response.json()["data"]["task_id"]
    assert len(queued) == 1
    assert queued[0][2]["stop_at"] == "video"


def test_create_video_rejects_missing_subject(client):
    """缺少必填主题时返回 400，不创建任务。"""
    response = client.post("/api/v1/videos", json={})
    assert response.status_code == 400


def test_generate_script_respects_paragraph_limit(mock_llm_model):
    """脚本生成器只返回请求数量的段落。"""
    from funvideo.app.services import llm

    mock_llm_model.chat.return_value = "第一段。\n\n第二段。"
    assert llm.generate_script("测试", paragraph_number=1) == "第一段。"


def test_upload_bgm_normalizes_filename_and_rejects_wrong_extension(client):
    """上传接口保存 MP3 基名，并拒绝伪装扩展名。"""
    from funvideo.app.utils import utils

    response = client.post(
        "/api/v1/musics",
        files={"file": ("../track.mp3", b"ID3", "audio/mpeg")},
    )
    assert response.status_code == 200
    saved_file = Path(response.json()["data"]["file"])
    assert saved_file.name == "track.mp3"
    assert saved_file.parent.resolve() == Path(utils.song_dir()).resolve()

    rejected = client.post(
        "/api/v1/musics",
        files={"file": ("track.mp3.exe", b"not audio", "application/octet-stream")},
    )
    assert rejected.status_code == 400


def test_download_and_range_stream_video(client):
    """下载与 Range 流接口可读取任务目录内的视频。"""
    from funvideo.app.utils import utils

    video_file = Path(utils.task_dir("api-test")) / "final.mp4"
    video_file.write_bytes(b"0123456789")

    downloaded = client.get("/api/v1/download/api-test/final.mp4")
    assert downloaded.status_code == 200
    assert downloaded.content == b"0123456789"

    streamed = client.get(
        "/api/v1/stream/api-test/final.mp4", headers={"Range": "bytes=2-5"}
    )
    assert streamed.status_code == 206
    assert streamed.content == b"2345"
    assert streamed.headers["content-range"] == "bytes 2-5/10"


def test_task_file_rejects_traversal():
    """任务文件解析拒绝访问任务目录之外的文件。"""
    from funvideo.app.controllers.v1.video import _resolve_task_file
    from funvideo.app.models.exception import HttpException

    with pytest.raises(HttpException):
        _resolve_task_file("../config.toml")
