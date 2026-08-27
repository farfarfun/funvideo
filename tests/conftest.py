"""pytest 全局配置：为 funvideo 冒烟测试提供隔离的运行环境。

funvideo 在导入期间存在两个副作用，需要在测试环境中妥善处理：

1. `funvideo.app.config.core.Config` 会在模块导入时基于**当前工作目录**读取
   `./config.toml`。仓库中并没有随附 `config.example.toml`，因此如果裸跑在
   仓库根目录下会直接在 import 阶段抛出 ``FileNotFoundError``。
2. `funvideo.app.services.llm` 在模块导入时会直接调用
   ``funai.llm.get_model("deepseek")`` 构造一个真实的 DeepSeek/OpenAI 兼容客户端，
   如果没有配置真实的 API Key，会在 import 阶段直接抛出 ``openai.OpenAIError``。

这里通过一个 session 级、autouse 的 fixture：
- 切换到一个临时目录，并预先放置一个空的 ``config.toml``（各配置项都有默认值，
  空文件即可正常解析）；
- 在任何测试首次触发 funvideo 服务层导入之前，替换掉 ``funai.llm.get_model``，
  避免真实网络请求 / 凭据校验。

之后各测试文件里对 funvideo 的 import 都必须放在测试函数体内（而不是模块顶层），
以保证这个 fixture 先生效。
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session", autouse=True)
def _funvideo_isolated_env():
    tmp_dir = tempfile.mkdtemp(prefix="funvideo_test_")
    old_cwd = os.getcwd()
    os.chdir(tmp_dir)
    (Path(tmp_dir) / "config.toml").write_text("", encoding="utf-8")

    # 在 funvideo.app.services.llm 被 import 之前，替换真实的大模型构造函数，
    # 避免冒烟测试依赖真实的 DeepSeek/OpenAI 凭据与网络访问。
    import funai.llm as funai_llm

    mock_model = MagicMock(name="mock_deepseek_model")
    mock_model.chat.return_value = "这是一段用于冒烟测试的模拟脚本内容。"
    funai_llm.get_model = lambda *args, **kwargs: mock_model

    try:
        yield mock_model
    finally:
        os.chdir(old_cwd)


@pytest.fixture(scope="session")
def fastapi_app(_funvideo_isolated_env):
    """导入并返回 funvideo 的 FastAPI 应用对象（app/asgi.py 中的 ``app``）。"""
    from funvideo.app.asgi import app

    return app


@pytest.fixture(scope="session")
def mock_llm_model(fastapi_app, _funvideo_isolated_env):
    """funvideo.app.services.llm.model 实际绑定的 mock 对象，供测试按需配置返回值。"""
    return _funvideo_isolated_env


@pytest.fixture()
def client(fastapi_app):
    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as test_client:
        yield test_client
