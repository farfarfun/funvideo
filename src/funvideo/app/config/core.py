import os
import shutil
import socket

import toml
from funutil import getLogger

logger = getLogger("funvideo")


class Config:
    def __init__(self, root_dir="./", config_file="./config.toml"):
        self._cfg = {}
        self.root_dir = root_dir
        self.config_file = config_file
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

    def load_config(self):
        if os.path.isdir(self.config_file):
            shutil.rmtree(self.config_file)

        if not os.path.isfile(self.config_file):
            example_file = f"{self.root_dir}/config.example.toml"
            if os.path.isfile(example_file):
                shutil.copyfile(example_file, self.config_file)
                logger.info("copy config.example.toml to config.toml")
        logger.info(f"load config from file: {self.config_file}")

        try:
            _config_ = toml.load(self.config_file)
        except Exception as e:
            logger.warning(f"load config failed: {str(e)}, try to load as utf-8-sig")
            with open(self.config_file, mode="r", encoding="utf-8-sig") as fp:
                _cfg_content = fp.read()
                _config_ = toml.loads(_cfg_content)
        self._cfg = _config_

    def save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            self._cfg["app"] = self.app
            self._cfg["azure"] = self.azure
            self._cfg["ui"] = self.ui
            f.write(toml.dumps(self._cfg))


config = Config()
