"""Validate arXiv specific metadata in knowledge entries.

Usage:
    python hooks/validate_arxiv.py <json_file> [json_file2 ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from validate_json import expand_inputs


EXPECTED_SOURCE = "arxiv"
ARXIV_ABS_URL = re.compile(r"^https://arxiv\.org/abs/\d{4}\.\d{4,5}(?:v\d+)?$")
ARXIV_PDF_URL = re.compile(r"^https://arxiv\.org/pdf/\d{4}\.\d{4,5}(?:v\d+)?\.pdf$")
PAPER_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
BASE_ID = re.compile(r"^\d{4}\.\d{4,5}$")
REQUIRED_CATEGORIES = {"cs.AI", "cs.CL"}


def load_json(file_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load one JSON object and return parse errors instead of raising."""
    if not file_path.exists():
        return None, [f"{file_path}: file does not exist"]

    if not file_path.is_file():
        return None, [f"{file_path}: path is not a file"]

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        return None, [f"{file_path}: file is not valid UTF-8: {exc}"]
    except json.JSONDecodeError as exc:
        return None, [
            f"{file_path}: invalid JSON at line {exc.lineno}, col {exc.colno}"
        ]

    if not isinstance(data, dict):
        return None, [f"{file_path}: root JSON value must be an object"]

    return data, []


def validate_string_list(
    value: Any,
    field_name: str,
    file_path: Path,
) -> list[str]:
    """Validate that a metadata field is a list of strings."""
    errors: list[str] = []

    if not isinstance(value, list):
        return [f"{file_path}: field '{field_name}' must be list"]

    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{file_path}: field '{field_name}[{index}]' must be str")

    return errors


def validate_arxiv_entry(data: dict[str, Any], file_path: Path) -> list[str]:
    """Validate fields that only make sense for arXiv entries."""
    errors: list[str] = []

    if data.get("source") != EXPECTED_SOURCE:
        errors.append(
            f"{file_path}: field 'source' must be '{EXPECTED_SOURCE}'"
        )

    source_url = data.get("source_url")
    if not isinstance(source_url, str) or not ARXIV_ABS_URL.fullmatch(source_url):
        errors.append(
            f"{file_path}: field 'source_url' must be an arXiv abs URL"
        )

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return errors + [f"{file_path}: field 'metadata' must be object"]

    paper_id = metadata.get("paper_id")
    if not isinstance(paper_id, str) or not PAPER_ID.fullmatch(paper_id):
        errors.append(f"{file_path}: field 'metadata.paper_id' is invalid")

    base_id = metadata.get("base_id")
    if not isinstance(base_id, str) or not BASE_ID.fullmatch(base_id):
        errors.append(f"{file_path}: field 'metadata.base_id' is invalid")

    pdf_url = metadata.get("pdf_url")
    if not isinstance(pdf_url, str) or not ARXIV_PDF_URL.fullmatch(pdf_url):
        errors.append(f"{file_path}: field 'metadata.pdf_url' is invalid")

    categories = metadata.get("categories")
    errors.extend(validate_string_list(categories, "metadata.categories", file_path))
    if isinstance(categories, list):
        category_set = {item for item in categories if isinstance(item, str)}
        if not category_set & REQUIRED_CATEGORIES:
            errors.append(
                f"{file_path}: field 'metadata.categories' must include "
                "cs.AI or cs.CL"
            )

    return errors


def validate_file(file_path: Path) -> list[str]:
    """Validate one arXiv knowledge entry."""
    data, errors = load_json(file_path)
    if errors or data is None:
        return errors

    return validate_arxiv_entry(data, file_path)


def print_usage() -> None:
    """Print the command format when input is missing."""
    print("Usage: python hooks/validate_arxiv.py <json_file> [json_file2 ...]")


def main(argv: list[str]) -> int:
    """Run arXiv-specific validation and return an exit code."""
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

    if all_errors:
        print("arXiv validation failed:")
        for error in all_errors:
            print(f"- {error}")
    else:
        print("arXiv validation passed.")

    print(
        "Summary: "
        f"checked={checked_count}, "
        f"passed={checked_count - failed_files}, "
        f"failed={failed_files}, "
        f"errors={len(all_errors)}"
    )

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
