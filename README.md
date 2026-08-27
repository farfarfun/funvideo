# funvideo

短视频自动生成服务（基于 [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) 二次封装）：给定一个主题，用 LLM 生成文案和关键词，再从 Pexels / Pixabay / 本地素材抓取视频片段，配上 TTS 语音、字幕和背景音乐，最终合成一条短视频。提供 FastAPI 接口服务和一个 Streamlit 可视化界面两种使用方式。

## 安装

```bash
pip install funvideo
```

## 作为服务运行

```bash
uvicorn funvideo.app.asgi:app --host 0.0.0.0 --port 8080
```

启动后可在 `http://127.0.0.1:8080/docs` 查看接口文档。运行目录下需要一个 `config.toml`（`funvideo.app.config.core.Config` 负责加载，支持 LLM/Pexels/Pixabay/Azure 语音等参数）。主要接口（见 `src/funvideo/app/router.py`）：

- `POST /api/v1/scripts`：调用 `services/llm.py` 生成视频文案
- `POST /api/v1/terms`：根据文案生成视频检索关键词
- `POST /api/v1/videos`：提交完整的视频生成任务（文案 → 素材 → 语音 → 字幕 → 合成，见 `services/task.py`）
- `POST /api/v1/subtitle`、`POST /api/v1/audio`：只生成字幕或只生成语音的任务
- `GET/DELETE /api/v1/tasks/{task_id}`：查询 / 删除任务
- `GET/POST /api/v1/musics`：查询、上传背景音乐
- `GET /api/v1/stream/{file_path}`、`GET /api/v1/download/{file_path}`：在线播放 / 下载生成的视频

任务支持内存或 Redis 两种任务管理器（`controllers/manager/`），由 `config.toml` 中的 `enable_redis` 开关控制。

## 作为 Web UI 运行

```bash
streamlit run src/funvideo/webui/Main.py
```

提供一个可视化界面，可配置 LLM 供应商（OpenAI、DeepSeek、Moonshot、Qwen、Gemini、Ollama 等）、视频来源、字幕样式、语音音色等，点击生成后直接在页面预览视频。

## 核心依赖

视频合成基于 `moviepy`，语音合成使用 `edge-tts`（默认）或 Azure 语音，字幕识别用到 `faster-whisper`；素材下载、字体/背景音乐随机选取分别复用了 [`funmaterial`](https://github.com/farfarfun/funmaterial) 和 [`funtalk`](https://github.com/farfarfun/funtalk) 两个库。
