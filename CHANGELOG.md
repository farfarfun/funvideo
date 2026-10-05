# 更新日志

## 未发布

### 修复

- `requires-python` 与 Ruff target 降为组织统一下限 `>=3.10`。
- `scripts/setup.sh` 基于脚本自身位置解析 `ROOT_DIR`，不再依赖调用者的工作目录；
  `status` 命令支持省略环境参数、默认汇报 `dev`/`prod` 全部状态。
- `server run prod` / `start prod` 增加正式发行包安装校验，拒绝源码或可编辑安装启动生产服务。
- `server stop` 改为校验 PID 文件对应进程身份后直接按 PID 发信号，不再用端口探测代替进程归属校验。
- `llm.py` 生成脚本/检索词失败时不再静默返回空字符串或空列表，改为抛出 `LLMGenerationError`
  并由控制器转换为明确的 502 响应；收窄为可恢复的网络/解析异常。
- `install-prod`、`upgrade`、`rollback` 统一改走 `uv tool`，不再直接调用 `pip`。
- `.gitignore` 补充 `*.rar`。
- 公开服务/视频/字幕函数补齐类型标注与中文 docstring；`webui/Main.py` 重命名为 `webui/main.py`。
- `tests/test_cli.py` 按 `conftest.py` 约定，将 `funvideo` 导入移入各测试函数体内。
- 修复 `ruff` 对 `cli.py` 的 import 排序与两处超长行格式问题。

## 1.0.25 - 2026-09-20

### 新增

- 增加顶层 Python 包和 `py.typed` 类型标记。
- 增加 MoneyPrinterTurbo 原始版权与 MIT 许可声明。
- 增加统一的 `funvideo` 服务、WebUI 与包管理命令，以及 `scripts/setup.sh` 生命周期入口。

### 修复

- 显式声明 Hatchling 构建后端，确保源码包与 wheel 可重复构建。
- 补齐项目的 MIT 许可证元数据。
- 修复规则网格之外的服务配置、密钥落盘、静默异常及文件路径校验问题。

### 变更

- 停止跟踪运行时生成的压缩日志。
- 统一使用 farlog，并删除未引用的旧语音与备份配置实现。

### 废弃

- 无。
