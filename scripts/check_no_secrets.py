#!/usr/bin/env python3
"""Block committed secrets and tracked local env files."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ENV_TEMPLATES = {".env.example", ".env.test.example"}
SECRET_ENV_VARS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GITHUB_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
}
ENV_LIKE_SUFFIXES = {".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml", ".ini"}
TOKEN_PATTERNS = (
    ("OpenAI-like key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
)
PLACEHOLDER_MARKERS = (
    "your-",
    "your_",
    "example",
    "xxxx",
    "xxxxx",
    "placeholder",
    "changeme",
    "replace_me",
    "replace-with",
    "dummy",
    "sample",
    "修改为真实",
    "...",
)


@dataclass(frozen=True)
class SecretIssue:
    path: str
    line_no: int
    reason: str
    detail: str


def is_tracked_local_env_file(path: Path) -> bool:
    if path.name in ALLOWED_ENV_TEMPLATES:
        return False
    return path.name == ".env" or path.name.startswith(".env.")


def is_env_like_file(path: Path) -> bool:
    return path.name.startswith(".env") or path.suffix in ENV_LIKE_SUFFIXES


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    if lowered.startswith("$") or lowered.startswith("${") or lowered.startswith("<"):
        return True
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def mask(value: str) -> str:
    if len(value) <= 8:
        return value[:2] + "..."
    return f"{value[:4]}...{value[-4:]}"


def read_text_file(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    if b"\x00" in raw:
        return None

    return raw.decode("utf-8", errors="ignore")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def scan_path(path: Path) -> list[SecretIssue]:
    issues: list[SecretIssue] = []

    if not path.exists() or not path.is_file():
        return issues

    rel_path = display_path(path)
    if is_tracked_local_env_file(path):
        issues.append(
            SecretIssue(
                path=str(rel_path),
                line_no=1,
                reason="Tracked local env file",
                detail="Commit only example templates; keep local overrides untracked.",
            )
        )

    text = read_text_file(path)
    if text is None:
        return issues

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        env_match = re.match(r"([A-Z0-9_]+)\s*=\s*(.+)", stripped)
        if env_match and is_env_like_file(path):
            key, raw_value = env_match.groups()
            value = raw_value.split("#", 1)[0].strip().strip("'\"")
            if key in SECRET_ENV_VARS and not is_placeholder(value):
                issues.append(
                    SecretIssue(
                        path=str(rel_path),
                        line_no=line_no,
                        reason=f"Hardcoded {key}",
                        detail=mask(value),
                    )
                )

        for label, pattern in TOKEN_PATTERNS:
            match = pattern.search(line)
            if match and not is_placeholder(match.group(0)):
                issues.append(
                    SecretIssue(
                        path=str(rel_path),
                        line_no=line_no,
                        reason=label,
                        detail=mask(match.group(0)),
                    )
                )
    return issues


def default_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def normalize_paths(items: Sequence[str]) -> list[Path]:
    if not items:
        return default_paths()

    paths: list[Path] = []
    for item in items:
        path = Path(item)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        paths.append(path)
    return paths


def collect_issues(paths: Iterable[Path]) -> list[SecretIssue]:
    issues: list[SecretIssue] = []
    for path in paths:
        issues.extend(scan_path(path))
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail when tracked files contain real secrets.")
    parser.add_argument("paths", nargs="*", help="Optional file paths to scan. Defaults to tracked files.")
    args = parser.parse_args(argv)

    issues = collect_issues(normalize_paths(args.paths))
    if not issues:
        print("No committed secrets detected.")
        return 0

    print("Committed secret check failed:")
    for issue in issues:
        print(f"- {issue.path}:{issue.line_no} [{issue.reason}] {issue.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
