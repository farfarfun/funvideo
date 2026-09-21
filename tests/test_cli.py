from pathlib import Path

from typer.testing import CliRunner

from funvideo import cli

runner = CliRunner()


def test_cli_exposes_service_and_package_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for command in ("server", "webui", "upgrade", "rollback", "uninstall"):
        assert command in result.output

    result = runner.invoke(cli.app, ["server", "--help"])
    assert result.exit_code == 0
    for command in ("start", "run", "stop", "restart", "status"):
        assert command in result.output


def test_server_options_prefer_cli_over_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'listen_host = "127.0.0.2"\nlisten_port = 9000\n', encoding="utf-8"
    )

    assert cli._resolve_server_options(config, None, None) == ("127.0.0.2", 9000)
    assert cli._resolve_server_options(config, "0.0.0.0", 8080) == (
        "0.0.0.0",
        8080,
    )
