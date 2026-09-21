import json
import os
import shutil
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import toml
from farlog import getLogger
from funsecret import read_secret, write_secret

logger = getLogger("funvideo")


class Config:
    """加载应用配置，并将敏感值交给 funsecret 管理。"""

    def __init__(self, root_dir: str = "./", config_file: str | None = None) -> None:
        self._cfg = {}
        self.root_dir = root_dir
        self.config_file = (
            config_file
            if config_file is not None
            else os.getenv("FUNVIDEO_CONFIG_FILE", "./config.toml")
        )
        self.load_config()

        self.hostname = socket.gethostname()
        self.app = self._cfg.get("app", {})
        self.whisper = self._cfg.get("whisper", {})
        self.proxy = self._cfg.get("proxy", {})
        self.azure = self._cfg.get("azure", {})
        self.ui = self._cfg.get("ui", {})

        self.log_level = self._cfg.get("log_level", "DEBUG")
        self.listen_host = self._cfg.get("listen_host", "0.0.0.0")
        self.listen_port = self._cfg.get("listen_port", 8080)
        self.project_name = self._cfg.get("project_name", "MoneyPrinterTurbo")
        self.project_description = ""
        self.project_version = self._cfg.get("project_version", "1.2.1")
        self.reload_debug = False

        imagemagick_path = self.app.get("imagemagick_path", "")
        if imagemagick_path and os.path.isfile(imagemagick_path):
            os.environ["IMAGEMAGICK_BINARY"] = imagemagick_path

        ffmpeg_path = self.app.get("ffmpeg_path", "")
        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path

        logger.info(f"{self.project_name} v{self.project_version}")

    @staticmethod
    def _env_value(value: str) -> Any:
        value = value.strip()
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip("'\"")

    @classmethod
    def _load_env(cls, config_file: Path) -> dict[str, Any]:
        config: dict[str, Any] = {}
        for line_number, raw_line in enumerate(
            config_file.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                raise ValueError(
                    f"invalid .env line {line_number} in {config_file}: {raw_line}"
                )
            key, value = line.split("=", 1)
            key = key.strip()
            if key.upper().startswith("FUNVIDEO_"):
                key = key[len("FUNVIDEO_") :]
            parts = [part.strip().lower() for part in key.split("__") if part.strip()]
            if not parts:
                raise ValueError(
                    f"invalid .env key on line {line_number} in {config_file}"
                )
            target = config
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = cls._env_value(value)
        return config

    @classmethod
    def _read_config(cls, config_file: Path) -> dict[str, Any]:
        suffix = config_file.suffix.lower()
        if suffix == ".toml":
            data = toml.loads(config_file.read_text(encoding="utf-8-sig"))
        elif suffix == ".json":
            data = json.loads(config_file.read_text(encoding="utf-8-sig"))
        elif suffix == ".env":
            data = cls._load_env(config_file)
        else:
            raise ValueError(
                f"unsupported config format {suffix or '<none>'}; "
                "expected .toml, .json, or .env"
            )
        if not isinstance(data, dict):
            raise TypeError(f"config root must be an object: {config_file}")
        return data

    def load_config(self) -> None:
        """从显式路径、环境变量或默认 TOML 路径加载配置。"""
        config_file = Path(self.config_file)
        if config_file.suffix.lower() not in {".toml", ".json", ".env"}:
            raise ValueError(
                f"unsupported config format {config_file.suffix or '<none>'}; "
                "expected .toml, .json, or .env"
            )
        if os.path.isdir(self.config_file):
            raise IsADirectoryError(f"config path is a directory: {self.config_file}")

        if not config_file.is_file() and config_file.suffix.lower() == ".toml":
            example_file = Path(self.root_dir) / "config.example.toml"
            if example_file.is_file():
                config_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(example_file, config_file)
                logger.info("copy config.example.toml to config.toml")
        logger.info(f"load config from file: {self.config_file}")
        self._cfg = self._read_config(config_file) if config_file.is_file() else {}

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        return key.lower().endswith(
            ("api_key", "api_keys", "secret_key", "speech_key", "password", "token")
        )

    @classmethod
    def _without_secrets(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: cls._without_secrets(item)
                for key, item in value.items()
                if not cls._is_secret_key(str(key))
            }
        if isinstance(value, list):
            return [cls._without_secrets(item) for item in value]
        return value

    def get_secret(self, section: str, key: str, default: Any = None) -> Any:
        """读取密钥，优先使用环境变量，其次使用 funsecret。"""
        env_key = f"FUNVIDEO_{section}_{key}".upper()
        if env_key in os.environ:
            return os.environ[env_key]
        try:
            value = read_secret("funvideo", section, key)
        except Exception as exc:
            logger.warning(f"read secret failed for {section}.{key}: {exc}")
            value = None
        if value is not None:
            return value
        return default

    def set_secret(self, section: str, key: str, value: str | None) -> None:
        """将非空密钥写入 funsecret，不修改普通配置字典。"""
        if value:
            write_secret(value, "funvideo", section, key)

    @staticmethod
    def _flatten_env(value: Mapping[str, Any], prefix: str = "") -> list[str]:
        lines = []
        for key, item in value.items():
            env_key = f"{prefix}__{key}" if prefix else str(key)
            if isinstance(item, Mapping):
                lines.extend(Config._flatten_env(item, env_key))
            else:
                encoded = item if isinstance(item, str) else json.dumps(item)
                lines.append(f"{env_key.upper()}={encoded}")
        return lines

    def save_config(self) -> None:
        """保存非敏感配置；密钥字段始终从输出中剔除。"""
        config = dict(self._cfg)
        config["app"] = self.app
        config["azure"] = self.azure
        config["ui"] = self.ui
        config = self._without_secrets(config)
        config_file = Path(self.config_file)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        suffix = config_file.suffix.lower()
        if suffix == ".toml":
            content = toml.dumps(config)
        elif suffix == ".json":
            content = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        elif suffix == ".env":
            content = "\n".join(self._flatten_env(config)) + "\n"
        else:
            raise ValueError(
                f"unsupported config format {suffix or '<none>'}; "
                "expected .toml, .json, or .env"
            )
        config_file.write_text(content, encoding="utf-8")


config = Config()
