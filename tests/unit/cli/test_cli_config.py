"""Test detent config subcommand group."""

from click.testing import CliRunner

from detent.cli import main


def test_config_validate_valid_yaml(tmp_path):
    """config validate should exit 0 for a valid detent.yaml."""
    runner = CliRunner()
    config_file = tmp_path / "detent.yaml"
    config_file.write_text("policy: standard\n")
    result = runner.invoke(main, ["--config", str(config_file), "config", "validate"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_config_validate_invalid_yaml(tmp_path):
    """config validate should exit 1 for structurally invalid config."""
    runner = CliRunner()
    config_file = tmp_path / "detent.yaml"
    config_file.write_text("proxy:\n  port: notanumber\n")
    result = runner.invoke(main, ["--config", str(config_file), "config", "validate"])
    assert result.exit_code == 1


def test_config_validate_missing_file(tmp_path):
    """config validate with non-existent file should exit 1."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(tmp_path / "missing.yaml"), "config", "validate"],
    )
    assert result.exit_code == 1


def test_config_show_prints_yaml(tmp_path):
    """config show should pretty-print resolved config as YAML."""
    import yaml

    runner = CliRunner(mix_stderr=False)
    config_file = tmp_path / "detent.yaml"
    config_file.write_text("policy: strict\n")
    result = runner.invoke(main, ["--config", str(config_file), "config", "show"])
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.output)
    assert parsed["policy"] == "strict"
