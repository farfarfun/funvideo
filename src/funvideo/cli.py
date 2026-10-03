"""funvideo 服务与包管理命令行入口。"""

import json
import os
import subprocess
import sys
import time
from enum import Enum
from importlib.metadata import (
    PackageNotFoundError,
    distribution,
    version as package_version,
)
from pathlib import Path
from typing import Annotated, Any, NoReturn

import toml
import typer

PACKAGE_NAME = "funvideo"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
STOP_TIMEOUT_SECONDS = 10


class Environment(str, Enum):
    """服务运行环境。"""

    dev = "dev"
    prod = "prod"


app = typer.Typer(help="funvideo 短视频生成服务")
server_app = typer.Typer(help="服务生命周期", no_args_is_help=True)
app.add_typer(server_app, name="server")


def _version() -> str:
    return package_version(PACKAGE_NAME)


def _fail(message: str) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _ok(message: str) -> None:
    typer.secho(message, fg=typer.colors.GREEN)


def _warn(message: str) -> None:
    typer.secho(message, fg=typer.colors.YELLOW)


def _default_state_dir() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "farfarfun" / PACKAGE_NAME


def _default_config_path() -> Path:
    return _default_state_dir() / "config.toml"


def _runtime_dir() -> Path:
    configured_path = os.environ.get("FUNVIDEO_RUNTIME_DIR")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "farfarfun" / PACKAGE_NAME / ".run"


def _active_config_file(environment: Environment) -> Path:
    return _runtime_dir() / f"{PACKAGE_NAME}-{environment.value}.config"


def _read_active_config(environment: Environment) -> Path | None:
    pointer = _active_config_file(environment)
    if not pointer.is_file():
        return None
    value = pointer.read_text(encoding="utf-8").strip()
    return Path(value) if value else None


def _resolve_config_path(
    config: Path | None,
    *,
    environment: Environment,
    use_active: bool = False,
) -> Path:
    path = config or (_read_active_config(environment) if use_active else None)
    return (path or _default_config_path()).expanduser().resolve()


def _state_paths(environment: Environment) -> tuple[Path, Path]:
    prefix = _runtime_dir() / f"{PACKAGE_NAME}-{environment.value}"
    return prefix.with_suffix(".pid"), prefix.with_suffix(".log")


def _read_pid(environment: Environment) -> int | None:
    pid_file, _ = _state_paths(environment)
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    return pid if pid > 1 else None


def _pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_is_managed_server(pid: int) -> bool:
    """检查 PID 是否是本 CLI 启动的 funvideo 服务进程。"""
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().decode().replace("\0", " ")
    except OSError:
        return False
    return PACKAGE_NAME in command and "server run" in command


def _require_official_installation() -> None:
    """拒绝以本地路径或可编辑安装的包启动生产服务。"""
    try:
        package = distribution(PACKAGE_NAME)
    except PackageNotFoundError:
        _fail("生产服务必须使用从正式发布源安装的 funvideo 包")
    if package.read_text("direct_url.json") is not None:
        _fail("生产服务不能使用本地路径或可编辑安装的 funvideo 包")


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"无效的 .env 配置行：{raw_line}")
        values[key.strip().lower()] = value.strip().strip("\"'")
    return values


def _load_server_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = toml.loads(path.read_text(encoding="utf-8-sig"))
    elif suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    elif suffix == ".env":
        data = _load_env(path)
    else:
        raise ValueError(f"不支持的配置文件格式：{suffix}（仅支持 .toml/.json/.env）")
    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是对象：{path}")
    return {str(key).lower(): value for key, value in data.items()}


def _resolve_server_options(
    config: Path, host: str | None, port: int | None
) -> tuple[str, int]:
    try:
        values = _load_server_config(config)
        resolved_host = host or str(
            values.get("listen_host") or values.get("host") or DEFAULT_HOST
        )
        resolved_port = int(
            port
            if port is not None
            else values.get("listen_port") or values.get("port") or DEFAULT_PORT
        )
    except (OSError, ValueError) as error:
        _fail(f"读取配置失败（{config}）：{error}")
    if not 1 <= resolved_port <= 65535:
        _fail(f"端口必须在 1-65535 之间：{resolved_port}")
    return resolved_host, resolved_port


def _write_state(config: Path, environment: Environment, pid: int) -> None:
    pid_file, _ = _state_paths(environment)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{pid}\n", encoding="utf-8")
    pointer = _active_config_file(environment)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"{config}\n", encoding="utf-8")


def _clear_state(config: Path, environment: Environment) -> None:
    pid_file, _ = _state_paths(environment)
    pid_file.unlink(missing_ok=True)
    pointer = _active_config_file(environment)
    if _read_active_config(environment) == config:
        pointer.unlink(missing_ok=True)


def _server_command_options(
    environment: Environment, config: Path, host: str | None, port: int | None
) -> list[str]:
    options = [environment.value, "--config", str(config)]
    if host is not None:
        options += ["--host", host]
    if port is not None:
        options += ["--port", str(port)]
    return options


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    show_version: Annotated[
        bool, typer.Option("--version", help="显示版本号后退出")
    ] = False,
) -> None:
    """显示帮助或版本信息。"""
    if show_version:
        typer.echo(_version())
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("webui")
def webui() -> None:
    """运行可选的 Streamlit Web 界面。"""
    script = Path(__file__).parent / "webui" / "main.py"
    result = subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(script)], check=False
    )
    if result.returncode != 0:
        _fail('WebUI 启动失败；请先安装 `pip install "funvideo[webui]"`')


@server_app.command("run")
def server_run(
    environment: Annotated[Environment, typer.Argument(help="运行环境：dev 或 prod")],
    host: Annotated[str | None, typer.Option(help="监听地址")] = None,
    port: Annotated[int | None, typer.Option(help="监听端口")] = None,
    config: Annotated[
        Path | None, typer.Option(help=".toml、.json 或 .env 配置文件")
    ] = None,
) -> None:
    """在前台运行 API 服务。"""
    if environment is Environment.prod:
        _require_official_installation()
    resolved_config = _resolve_config_path(config, environment=environment)
    resolved_host, resolved_port = _resolve_server_options(resolved_config, host, port)
    existing = _read_pid(environment)
    if existing is not None and existing != os.getpid() and _pid_is_live(existing):
        _fail(f"funvideo 已在运行（pid {existing}）")

    os.environ["FUNVIDEO_CONFIG_FILE"] = str(resolved_config)
    os.environ["FUNVIDEO_ENV"] = environment.value
    _write_state(resolved_config, environment, os.getpid())
    try:
        import uvicorn

        uvicorn.run(
            "funvideo.app.asgi:app",
            host=resolved_host,
            port=resolved_port,
            log_level="warning",
        )
    finally:
        _clear_state(resolved_config, environment)


@server_app.command("start")
def server_start(
    environment: Annotated[Environment, typer.Argument(help="运行环境：dev 或 prod")],
    host: Annotated[str | None, typer.Option(help="监听地址")] = None,
    port: Annotated[int | None, typer.Option(help="监听端口")] = None,
    config: Annotated[
        Path | None, typer.Option(help=".toml、.json 或 .env 配置文件")
    ] = None,
) -> None:
    """在后台启动 API 服务。"""
    active_config = _read_active_config(environment)
    if active_config is not None:
        active_pid = _read_pid(environment)
        if active_pid is not None and _pid_is_live(active_pid):
            _fail(f"funvideo 已在运行（pid {active_pid}）")

    resolved_config = _resolve_config_path(config, environment=environment)
    _, resolved_port = _resolve_server_options(resolved_config, host, port)
    _, log_file = _state_paths(environment)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "funvideo.cli",
        "server",
        "run",
        *_server_command_options(environment, resolved_config, host, port),
    ]
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(1)
    if process.poll() is not None:
        _clear_state(resolved_config, environment)
        _fail(f"funvideo 启动失败，请查看日志：{log_file}")
    _ok(f"funvideo 已启动（pid {process.pid}，端口 {resolved_port}，日志 {log_file}）")


@server_app.command("stop")
def server_stop(
    environment: Annotated[Environment, typer.Argument(help="运行环境：dev 或 prod")],
    port: Annotated[int | None, typer.Option(help="监听端口")] = None,
    config: Annotated[Path | None, typer.Option(help="启动时使用的配置文件")] = None,
) -> None:
    """停止后台 API 服务。"""
    resolved_config = _resolve_config_path(
        config, environment=environment, use_active=True
    )
    pid_file, _ = _state_paths(environment)
    pid = _read_pid(environment)
    if pid is None or not _pid_is_live(pid):
        _clear_state(resolved_config, environment)
        _warn("funvideo 未在运行")
        return

    if not _pid_is_managed_server(pid):
        _fail(f"PID 文件不属于 funvideo 服务，拒绝停止（PID 文件：{pid_file}）")
    os.kill(pid, 15)

    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while _pid_is_live(pid):
        if time.monotonic() >= deadline:
            _fail(f"funvideo 在 {STOP_TIMEOUT_SECONDS}s 内未退出（pid {pid}）")
        time.sleep(0.2)
    _clear_state(resolved_config, environment)
    _ok("funvideo 已停止")


@server_app.command("restart")
def server_restart(
    environment: Annotated[Environment, typer.Argument(help="运行环境：dev 或 prod")],
    host: Annotated[str | None, typer.Option(help="监听地址")] = None,
    port: Annotated[int | None, typer.Option(help="监听端口")] = None,
    config: Annotated[
        Path | None, typer.Option(help=".toml、.json 或 .env 配置文件")
    ] = None,
) -> None:
    """停止后重新启动 API 服务。"""
    server_stop(environment=environment, port=port, config=config)
    server_start(environment=environment, host=host, port=port, config=config)


@server_app.command("status")
def server_status(
    environment: Annotated[
        Environment | None, typer.Argument(help="运行环境：dev 或 prod；省略时显示全部")
    ] = None,
    port: Annotated[int | None, typer.Option(help="监听端口")] = None,
    config: Annotated[Path | None, typer.Option(help="启动时使用的配置文件")] = None,
) -> None:
    """显示 API 服务状态和已安装版本。"""
    for current_environment in (environment,) if environment else tuple(Environment):
        resolved_config = _resolve_config_path(
            config, environment=current_environment, use_active=True
        )
        pid = _read_pid(current_environment)
        _, resolved_port = _resolve_server_options(resolved_config, None, port)
        prefix = f"[{current_environment.value}] "
        if pid is not None and _pid_is_live(pid):
            _ok(f"{prefix}运行中（funvideo@{_version()}，pid {pid}，端口 {resolved_port}）")
        elif pid is not None:
            _warn(f"{prefix}PID 文件已失效（pid {pid}，funvideo@{_version()}）")
        else:
            _warn(f"{prefix}未在运行（funvideo@{_version()}）")


def _run_uv_tool(arguments: list[str]) -> None:
    command = ["uv", "tool", *arguments]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        _fail(f"uv tool 执行失败（退出码 {result.returncode}）")


@app.command("upgrade")
def upgrade(
    version: Annotated[
        str | None, typer.Argument(help="目标版本，省略则安装最新版")
    ] = None,
) -> None:
    """升级到最新版或指定版本。"""
    target = f"{PACKAGE_NAME}=={version}" if version else PACKAGE_NAME
    _run_uv_tool(["install", "--upgrade", target])


@app.command("rollback")
def rollback(version: Annotated[str, typer.Argument(help="要回退到的版本")]) -> None:
    """强制安装指定旧版本。"""
    _run_uv_tool(["install", "--force", f"{PACKAGE_NAME}=={version}"])


@app.command("uninstall")
def uninstall() -> None:
    """停止服务后卸载 funvideo。"""
    server_stop(environment=Environment.dev)
    server_stop(environment=Environment.prod)
    _run_uv_tool(["uninstall", PACKAGE_NAME])


if __name__ == "__main__":
    app()
