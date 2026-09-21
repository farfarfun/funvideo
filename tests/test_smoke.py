"""funvideo 服务与公开接口冒烟测试。

测试隔离真实 LLM、TTS、素材下载及视频渲染等外部服务，覆盖：

- 顶层包 / FastAPI app 对象可以被正常 import 和构建；
- 应用注册了预期的路由；
- 几个不依赖真实 LLM / TTS / 下载素材等外部服务的接口可以被 TestClient 正常调用；
- 真正需要调用大模型的接口，通过 conftest.py 里替换掉的 mock 模型来验证请求/响应
  链路是通的（不发真实网络请求）；
- 视频任务、上传下载等公开接口由独立测试通过 mock 隔离外部服务后覆盖。
"""

from fastapi import FastAPI


def test_import_top_level_package():
    """顶层包 funvideo 可以被正常导入。"""
    import funvideo  # noqa: F401
    import funvideo.app  # noqa: F401


def test_app_object_builds_with_routes(fastapi_app):
    """FastAPI app 对象能被成功构建，并且注册了路由。"""
    assert isinstance(fastapi_app, FastAPI)
    assert len(fastapi_app.routes) > 0

    # /docs /openapi.json 等自带路由 + 业务路由（video、llm）应该都在。
    route_paths = {getattr(r, "path", None) for r in fastapi_app.routes}
    assert "/openapi.json" in route_paths
    assert "/docs" in route_paths


def test_openapi_schema_endpoint(client):
    """GET /openapi.json 不依赖任何外部服务，验证应用能正常处理请求。"""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    # 业务路由应该出现在 openapi schema 中（前缀 /api/v1，见 controllers/v1/base.py）。
    assert any(path.startswith("/api/v1") for path in schema["paths"])


def test_docs_endpoint(client):
    """GET /docs（Swagger UI）应正常返回 200，无需真实后端服务。"""
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_musics_list_endpoint(client):
    """GET /api/v1/musics 只是本地 glob 文件列表，不需要真实凭据/网络。"""
    resp = client.get("/api/v1/musics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert "files" in body["data"]
    assert isinstance(body["data"]["files"], list)


def test_query_nonexistent_task_returns_404(client):
    """GET /api/v1/tasks/{task_id} 查询不存在的任务时应返回 404，走的是内存态管理器。"""
    resp = client.get("/api/v1/tasks/does-not-exist")
    assert resp.status_code == 404


def test_generate_video_script_endpoint_with_mocked_llm(client, mock_llm_model):
    """POST /api/v1/scripts 会调用 funvideo.app.services.llm.generate_script。

    真实实现会通过 funai 调用 DeepSeek 大模型；conftest.py 中已经把
    funai.llm.get_model 替换为 mock，因此这里验证的是请求/响应链路
    （FastAPI -> controller -> service -> 大模型客户端）是通的，而不是真实的
    大模型生成效果。
    """
    mock_llm_model.chat.return_value = "这是一段用于冒烟测试的模拟脚本内容。"

    resp = client.post(
        "/api/v1/scripts",
        json={"video_subject": "冒烟测试视频", "paragraph_number": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert "video_script" in body["data"]
    assert body["data"]["video_script"] != ""


def test_generate_video_terms_endpoint_with_mocked_llm(client, mock_llm_model):
    """POST /api/v1/terms 同样只验证链路联通，不校验真实语义。

    generate_terms 期望大模型返回一个 JSON 字符串数组；这里 mock 模型返回真实的
    JSON 数组文本，覆盖“正常解析”这条路径。
    """
    mock_llm_model.chat.return_value = '["mock term one", "mock term two"]'

    resp = client.post(
        "/api/v1/terms",
        json={
            "video_subject": "冒烟测试视频",
            "video_script": "这是脚本内容",
            "amount": 2,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["data"]["video_terms"] == ["mock term one", "mock term two"]


def test_cli_entrypoint_declared():
    """确认安装包暴露统一的 funvideo CLI。"""
    from pathlib import Path

    import toml

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = toml.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["funvideo"] == "funvideo.cli:app"
