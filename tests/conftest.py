"""pytest 全局配置：为 funvideo 冒烟测试提供隔离的运行环境。

这里通过一个 session 级、autouse 的 fixture：
- 指向隔离的 XDG 配置与数据目录，验证服务不依赖当前工作目录；
- 替换 ``funai.llm.get_model``，
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
    old_config_home = os.environ.get("XDG_CONFIG_HOME")
    old_data_home = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(Path(tmp_dir) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp_dir) / "data")

    # 在 funvideo.app.services.llm 被 import 之前，替换真实的大模型构造函数，
    # 避免冒烟测试依赖真实的 DeepSeek/OpenAI 凭据与网络访问。
    import funai.llm as funai_llm

    mock_model = MagicMock(name="mock_deepseek_model")
    mock_model.chat.return_value = "这是一段用于冒烟测试的模拟脚本内容。"
    funai_llm.get_model = lambda *args, **kwargs: mock_model

    try:
        yield mock_model
    finally:
        if old_config_home is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = old_config_home
        if old_data_home is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = old_data_home


@pytest.fixture(scope="session")
def fastapi_app(_funvideo_isolated_env):
    """导入并返回 funvideo 的 FastAPI 应用对象（app/asgi.py 中的 ``app``）。"""
    from funvideo.app.asgi import app

    return app


@pytest.fixture(scope="session")
def mock_llm_model(fastapi_app, _funvideo_isolated_env):
    """返回服务懒加载后复用的 mock 模型，供测试按需配置返回值。"""
    return _funvideo_isolated_env


@pytest.fixture()
def client(fastapi_app):
    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as test_client:
        yield test_client
