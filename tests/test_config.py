import json

import pytest


def test_config_path_priority_and_missing_file(tmp_path, monkeypatch):
    """显式路径优先于环境变量，缺失文件按空配置启动。"""
    from funvideo.app.config.core import Config

    env_config = tmp_path / "env.json"
    env_config.write_text('{"listen_port": 9001}', encoding="utf-8")
    explicit_config = tmp_path / "explicit.toml"
    explicit_config.write_text("listen_port = 9002\n", encoding="utf-8")
    monkeypatch.setenv("FUNVIDEO_CONFIG_FILE", str(env_config))

    assert Config(config_file=str(explicit_config)).listen_port == 9002
    assert Config().listen_port == 9001
    assert Config(config_file=str(tmp_path / "missing.toml")).app == {}


def test_config_defaults_are_local_and_non_debug(tmp_path):
    """缺少显式配置时使用安全的监听地址和日志级别。"""
    from funvideo.app.config.core import Config

    config = Config(config_file=str(tmp_path / "missing.toml"))
    assert config.listen_host == "127.0.0.1"
    assert config.log_level == "INFO"


def test_default_config_and_project_metadata_use_funvideo_paths(tmp_path, monkeypatch):
    """未指定配置时使用用户配置目录和当前包的公开名称。"""
    from funvideo.app.config.core import Config

    monkeypatch.delenv("FUNVIDEO_CONFIG_FILE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    config = Config()

    assert config.config_file == str(
        tmp_path / "config" / "farfarfun" / "funvideo" / "config.toml"
    )
    assert config.project_name == "funvideo"
    assert config.project_version == "1.0.25"


def test_config_reads_json_and_env(tmp_path):
    """JSON 和简单 KEY=VALUE 配置均能保留嵌套结构与基础类型。"""
    from funvideo.app.config.core import Config

    json_config = tmp_path / "config.json"
    json_config.write_text(
        json.dumps({"listen_port": 9010, "app": {"llm_provider": "deepseek"}}),
        encoding="utf-8",
    )
    env_config = tmp_path / "config.env"
    env_config.write_text(
        "FUNVIDEO_LISTEN_PORT=9011\nAPP__HIDE_CONFIG=true\nAPP__LLM_PROVIDER=ollama\n",
        encoding="utf-8",
    )

    assert Config(config_file=str(json_config)).app["llm_provider"] == "deepseek"
    loaded_env = Config(config_file=str(env_config))
    assert loaded_env.listen_port == 9011
    assert loaded_env.app == {"hide_config": True, "llm_provider": "ollama"}


def test_config_rejects_unsupported_format(tmp_path):
    """不支持的配置后缀返回明确错误。"""
    from funvideo.app.config.core import Config

    with pytest.raises(ValueError, match="expected .toml, .json, or .env"):
        Config(config_file=str(tmp_path / "config.yaml"))


def test_secrets_use_funsecret_and_never_persist(tmp_path, monkeypatch):
    """密钥写入 funsecret，普通配置保存时会删除遗留密钥。"""
    from funvideo.app.config import core

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[app]\nllm_provider = "deepseek"\ndeepseek_api_key = "legacy-secret"\n',
        encoding="utf-8",
    )
    secret_store = {}

    def read_secret(cate1, cate2, cate3):
        return secret_store.get((cate1, cate2, cate3))

    def write_secret(value, cate1, cate2, cate3):
        secret_store[(cate1, cate2, cate3)] = value

    monkeypatch.setattr(core, "read_secret", read_secret)
    monkeypatch.setattr(core, "write_secret", write_secret)
    config = core.Config(config_file=str(config_file))

    assert (
        config.get_secret("app", "deepseek_api_key", "safe-default") == "safe-default"
    )
    config.set_secret("app", "deepseek_api_key", "new-secret")
    assert config.get_secret("app", "deepseek_api_key") == "new-secret"
    assert config.app["deepseek_api_key"] == "legacy-secret"
    monkeypatch.setenv("FUNVIDEO_APP_DEEPSEEK_API_KEY", "environment-secret")
    assert config.get_secret("app", "deepseek_api_key") == "environment-secret"

    config.save_config()
    saved = config_file.read_text(encoding="utf-8")
    assert "new-secret" not in saved
    assert "legacy-secret" not in saved
    assert "llm_provider" in saved


def test_secret_storage_errors_are_not_hidden(tmp_path, monkeypatch):
    """密钥存储故障必须向调用方传播，不能降级成缺失值。"""
    from funvideo.app.config import core

    def fail_read(*args):
        raise PermissionError("secret store is not readable")

    monkeypatch.setattr(core, "read_secret", fail_read)
    config = core.Config(config_file=str(tmp_path / "missing.toml"))
    with pytest.raises(PermissionError, match="secret store is not readable"):
        config.get_secret("app", "deepseek_api_key")
