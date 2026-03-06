from pathlib import Path

from scripts.check_no_secrets import collect_issues, is_placeholder, scan_path


def test_placeholder_values_are_allowed(tmp_path: Path) -> None:
    env_example = tmp_path / ".env.test.example"
    env_example.write_text("OPENAI_API_KEY=your-api-key-here\n", encoding="utf-8")

    assert scan_path(env_example) == []
    assert is_placeholder("your-api-key-here")


def test_tracked_local_env_file_is_rejected(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text("LLM_MODEL=openai/gpt-5\n", encoding="utf-8")

    issues = scan_path(env_file)

    assert any(issue.reason == "Tracked local env file" for issue in issues)


def test_real_secret_value_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "settings.txt"
    target.write_text("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")

    issues = collect_issues([target])

    assert any(issue.reason == "OpenAI-like key" for issue in issues)


def test_source_code_env_lookup_is_not_rejected(tmp_path: Path) -> None:
    target = tmp_path / "config.py"
    target.write_text('OPENAI_API_KEY = _resolve_key("OPENAI_API_KEY")\n', encoding="utf-8")

    assert collect_issues([target]) == []
