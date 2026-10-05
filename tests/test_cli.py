from pathlib import Path

from typer.testing import CliRunner

runner = CliRunner()


def test_cli_exposes_service_and_package_commands() -> None:
    from funvideo import cli

    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for command in ("server", "webui", "upgrade", "rollback", "uninstall"):
        assert command in result.output

    result = runner.invoke(cli.app, ["server", "--help"])
    assert result.exit_code == 0
    for command in ("start", "run", "stop", "restart", "status"):
        assert command in result.output


def test_server_options_prefer_cli_over_config(tmp_path: Path) -> None:
    from funvideo import cli

    config = tmp_path / "config.toml"
    config.write_text(
        'listen_host = "127.0.0.2"\nlisten_port = 9000\n', encoding="utf-8"
    )

    assert cli._resolve_server_options(config, None, None) == ("127.0.0.2", 9000)
    assert cli._resolve_server_options(config, "0.0.0.0", 8080) == (
        "0.0.0.0",
        8080,
    )


def test_server_commands_require_environment_except_status() -> None:
    from funvideo import cli

    for command in ("start", "run", "stop", "restart"):
        result = runner.invoke(cli.app, ["server", command])
        assert result.exit_code != 0

    result = runner.invoke(cli.app, ["server", "status"])
    assert result.exit_code == 0
    assert "[dev]" in result.output
    assert "[prod]" in result.output


def test_runtime_files_are_kept_in_stable_state_directory(
    tmp_path: Path, monkeypatch
) -> None:
    from funvideo import cli

    monkeypatch.delenv("FUNVIDEO_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    pid_file, log_file = cli._state_paths(cli.Environment.prod)
    runtime_dir = tmp_path / "state" / "farfarfun" / "funvideo" / ".run"
    assert pid_file == runtime_dir / "funvideo-prod.pid"
    assert log_file == runtime_dir / "funvideo-prod.log"


def test_runtime_directory_can_be_set_by_service_script(
    tmp_path: Path, monkeypatch
) -> None:
    from funvideo import cli

    monkeypatch.setenv("FUNVIDEO_RUNTIME_DIR", str(tmp_path / "service-state"))
    pid_file, _ = cli._state_paths(cli.Environment.dev)
    assert pid_file == tmp_path / "service-state" / "funvideo-dev.pid"
