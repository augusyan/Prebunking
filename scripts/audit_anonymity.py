#!/usr/bin/env python3
"""Fail when an anonymous-review artifact contains common identity leaks."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules"}
BINARY_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
}
FORBIDDEN_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".pyc",
}
ALLOWED_REPOSITORIES = {
    "https://github.com/camel-ai/oasis.git",
}

TEXT_RULES = {
    "email address": re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    "private filesystem path": re.compile(
        r"(?:/Users/|/Volumes/|/home/|/mnt/|[A-Z]:\\Users\\)",
        re.IGNORECASE,
    ),
    "private IPv4 address": re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "personal code-hosting URL": re.compile(
        r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/"
        r"[^\s<>\"')]+",
        re.IGNORECASE,
    ),
    "credential-like value": re.compile(
        r"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|AKIA[0-9A-Z]{16}|BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY)"
    ),
}


def iter_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts)
    ]


def inspect_text(path: Path, text: str, findings: list[str]) -> None:
    relative = path.relative_to(ROOT)
    for label, pattern in TEXT_RULES.items():
        if label == "private IPv4 address" and path.name == "poetry.lock":
            # Dependency versions such as 10.3.2.106 resemble private IPv4 addresses.
            continue
        for match in pattern.finditer(text):
            value = match.group(0)
            if label == "personal code-hosting URL" and value in ALLOWED_REPOSITORIES:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{relative}:{line}: {label}: {value}")


def inspect_xlsx(path: Path, findings: list[str]) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith((".xml", ".rels")):
                    continue
                text = archive.read(name).decode("utf-8", errors="ignore")
                inspect_text(path, text, findings)
    except zipfile.BadZipFile:
        findings.append(f"{path.relative_to(ROOT)}: invalid XLSX archive")


def main() -> int:
    findings: list[str] = []

    for path in iter_files():
        relative = path.relative_to(ROOT)
        lower_name = path.name.lower()

        if relative == Path("scripts/audit_anonymity.py"):
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"{relative}: forbidden generated/credential file")
            continue
        if lower_name == ".env" or lower_name.startswith(".env."):
            if lower_name != ".env.example":
                findings.append(f"{relative}: environment file may contain secrets")
                continue
        if path.suffix.lower() == ".xlsx":
            inspect_xlsx(path, findings)
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("latin-1", errors="ignore")
        inspect_text(path, text, findings)

    if findings:
        print("Anonymous-release audit failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Anonymous-release audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
