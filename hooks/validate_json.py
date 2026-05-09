"""Validate knowledge entry JSON files.

Usage:
    python hooks/validate_json.py <json_file> [json_file2 ...]
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path
from typing import Any


# Required fields are kept in one map so presence and type checks stay together.
REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = {"draft", "review", "published", "archived"}
VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}

ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d{8}-\d{3}$")
URL_PATTERN = re.compile(r"^https?://\S+$")
WILDCARD_CHARS = set("*?[")


def has_wildcard(value: str) -> bool:
    """Return True when the argument should be expanded as a glob pattern."""
    return any(char in value for char in WILDCARD_CHARS)


def expand_inputs(args: list[str]) -> tuple[list[Path], list[str]]:
    """Expand files and glob patterns while preserving command-line order."""
    paths: list[Path] = []
    errors: list[str] = []
    seen: set[Path] = set()

    for arg in args:
        if has_wildcard(arg):
            # Python handles wildcard expansion consistently on every shell.
            matches = sorted(glob.glob(arg, recursive=True))
            if not matches:
                errors.append(f"{arg}: no files matched this pattern")
                continue
        else:
            matches = [arg]

        for match in matches:
            path = Path(match)
            normalized = path.resolve()
            if normalized in seen:
                continue
            seen.add(normalized)
            paths.append(path)

    return paths, errors


def describe_type(expected_type: type) -> str:
    """Create a short type name for human-readable error messages."""
    return expected_type.__name__


def validate_required_fields(data: dict[str, Any], file_path: Path) -> list[str]:
    """Check required fields for both existence and exact expected type."""
    errors: list[str] = []

    for field_name, expected_type in REQUIRED_FIELDS.items():
        if field_name not in data:
            errors.append(f"{file_path}: missing required field '{field_name}'")
            continue

        if not isinstance(data[field_name], expected_type):
            expected = describe_type(expected_type)
            actual = type(data[field_name]).__name__
            errors.append(
                f"{file_path}: field '{field_name}' must be {expected}, "
                f"got {actual}"
            )

    return errors


def validate_known_fields(data: dict[str, Any], file_path: Path) -> list[str]:
    """Validate field-specific business rules for a knowledge entry."""
    errors: list[str] = []

    entry_id = data.get("id")
    if isinstance(entry_id, str) and not ID_PATTERN.fullmatch(entry_id):
        errors.append(
            f"{file_path}: field 'id' must match "
            "{source}-{YYYYMMDD}-{NNN}, for example github-20260317-001"
        )

    status = data.get("status")
    if isinstance(status, str) and status not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        errors.append(f"{file_path}: field 'status' must be one of: {allowed}")

    source_url = data.get("source_url")
    if isinstance(source_url, str) and not URL_PATTERN.fullmatch(source_url):
        errors.append(f"{file_path}: field 'source_url' must be a valid URL")

    summary = data.get("summary")
    if isinstance(summary, str) and len(summary.strip()) < 20:
        errors.append(f"{file_path}: field 'summary' must be at least 20 chars")

    tags = data.get("tags")
    if isinstance(tags, list) and len(tags) < 1:
        errors.append(f"{file_path}: field 'tags' must contain at least 1 item")
    elif isinstance(tags, list):
        for index, tag in enumerate(tags, start=1):
            if not isinstance(tag, str):
                errors.append(
                    f"{file_path}: field 'tags[{index}]' must be str"
                )

    if "score" in data:
        score = data["score"]
        # bool is a subclass of int, so reject it explicitly for clean data.
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            errors.append(f"{file_path}: field 'score' must be a number")
        elif not 1 <= score <= 10:
            errors.append(f"{file_path}: field 'score' must be between 1 and 10")

    if "audience" in data:
        audience = data["audience"]
        if not isinstance(audience, str):
            errors.append(f"{file_path}: field 'audience' must be str")
        elif audience not in VALID_AUDIENCES:
            allowed = ", ".join(sorted(VALID_AUDIENCES))
            errors.append(
                f"{file_path}: field 'audience' must be one of: {allowed}"
            )

    if "metadata" in data and not isinstance(data["metadata"], dict):
        errors.append(f"{file_path}: field 'metadata' must be object")

    return errors


def validate_file(file_path: Path) -> list[str]:
    """Parse one JSON file and return every validation error found."""
    errors: list[str] = []

    if not file_path.exists():
        return [f"{file_path}: file does not exist"]

    if not file_path.is_file():
        return [f"{file_path}: path is not a file"]

    try:
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except UnicodeDecodeError as exc:
        return [f"{file_path}: file is not valid UTF-8: {exc}"]
    except json.JSONDecodeError as exc:
        return [
            f"{file_path}: invalid JSON at line {exc.lineno}, col {exc.colno}"
        ]

    if not isinstance(data, dict):
        return [f"{file_path}: root JSON value must be an object"]

    errors.extend(validate_required_fields(data, file_path))
    errors.extend(validate_known_fields(data, file_path))

    return errors


def print_usage() -> None:
    """Print the command format when input is missing."""
    print("Usage: python hooks/validate_json.py <json_file> [json_file2 ...]")


def main(argv: list[str]) -> int:
    """Run validation and return a process exit code."""
    if not argv:
        print_usage()
        return 1

    paths, input_errors = expand_inputs(argv)
    all_errors = list(input_errors)
    checked_count = 0
    failed_files = 0

    for path in paths:
        checked_count += 1
        file_errors = validate_file(path)
        if file_errors:
            failed_files += 1
            all_errors.extend(file_errors)

    passed_files = checked_count - failed_files

    if all_errors:
        print("Validation failed:")
        for error in all_errors:
            print(f"- {error}")
    else:
        print("Validation passed.")

    print(
        "Summary: "
        f"checked={checked_count}, "
        f"passed={passed_files}, "
        f"failed={failed_files}, "
        f"errors={len(all_errors)}"
    )

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
