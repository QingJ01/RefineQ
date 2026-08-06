"""Scan tracked text files for high-confidence credential formats."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    ".cjs",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {"Caddyfile", "Dockerfile", "Dockerfile.api", "Dockerfile.web"}
MAX_TEXT_BYTES = 5 * 1024 * 1024
SECRET_PATTERNS = {
    "private_key": re.compile(
        "-----BEGIN " + r"(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "provider_token": re.compile(r"\b" + "sk" + r"-[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bgh" + r"[pousr]_[A-Za-z0-9]{20,}\b"),
    "slack_token": re.compile(r"\bxox" + r"[baprs]-[A-Za-z0-9-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAK" + r"IA[0-9A-Z]{16}\b"),
    "google_api_key": re.compile(r"\bAI" + r"za[0-9A-Za-z_-]{35}\b"),
}


@dataclass(frozen=True, slots=True)
class SecretFinding:
    path: str
    line: int
    kind: str


def _is_text(path: Path) -> bool:
    return path.name in TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def scan_paths(paths: list[Path], *, root: Path) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    resolved_root = root.resolve()
    for path in paths:
        if not path.is_file() or not _is_text(path) or path.stat().st_size > MAX_TEXT_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            display_path = path.resolve().relative_to(resolved_root).as_posix()
        except ValueError:
            display_path = path.resolve().as_posix()
        for kind, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    SecretFinding(
                        path=display_path,
                        line=text.count("\n", 0, match.start()) + 1,
                        kind=kind,
                    )
                )
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind))


def scan_repository(root: Path) -> list[SecretFinding]:
    repository = root.expanduser().resolve()
    process = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    paths = [
        repository / item.decode("utf-8", errors="surrogateescape")
        for item in process.stdout.split(b"\0")
        if item
    ]
    return scan_paths(paths, root=repository)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    findings = scan_repository(repository)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: possible {finding.kind}")
    if findings:
        print(f"Secret scan failed with {len(findings)} finding(s).")
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
