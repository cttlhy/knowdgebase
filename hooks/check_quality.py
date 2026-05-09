"""Score knowledge entry JSON files across five quality dimensions.

Usage:
    python hooks/check_quality.py <json_file> [json_file2 ...]
"""

from __future__ import annotations

import glob
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_STATUSES = {"draft", "review", "published", "archived"}
STANDARD_TAGS = {
    "agent",
    "ai",
    "api",
    "arxiv",
    "automation",
    "benchmark",
    "browser",
    "code-generation",
    "coding-agent",
    "computer-vision",
    "data",
    "evaluation",
    "github",
    "geocoding",
    "llm",
    "machine-learning",
    "memory",
    "ml",
    "multi-agent",
    "nlp",
    "open-source",
    "rag",
    "reasoning",
    "research",
    "retrieval",
    "security",
    "spatial-reasoning",
    "tool-use",
    "workflow",
}
TECH_KEYWORDS = {
    "agent",
    "ai",
    "api",
    "json",
    "llm",
    "python",
    "rag",
    "模型",
    "算法",
    "推理",
    "自动化",
    "检索",
    "向量",
    "训练",
    "评估",
    "框架",
    "工具",
    "浏览器",
}
EMPTY_WORDS_ZH = {
    "赋能",
    "抓手",
    "闭环",
    "打通",
    "全链路",
    "底层逻辑",
    "颗粒度",
    "对齐",
    "拉通",
    "沉淀",
    "强大的",
    "革命性的",
}
EMPTY_WORDS_EN = {
    "groundbreaking",
    "revolutionary",
    "game-changing",
    "cutting-edge",
    "disruptive",
    "next-generation",
    "world-class",
}
TIMESTAMP_FIELDS = {
    "created_at",
    "updated_at",
    "published_at",
    "collected_at",
    "date",
}

ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d{8}-\d{3}$")
URL_PATTERN = re.compile(r"^https?://\S+$")
DATE_PATTERN = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{8})")
WILDCARD_CHARS = set("*?[")


@dataclass
class DimensionScore:
    """Score and explanation for one quality dimension."""

    name: str
    score: float
    max_score: int
    detail: str


@dataclass
class QualityReport:
    """Full quality report for one JSON file."""

    path: Path
    dimensions: list[DimensionScore]
    total_score: float
    grade: str
    errors: list[str]


def has_wildcard(value: str) -> bool:
    """Return True when the argument should be expanded as a glob pattern."""
    return any(char in value for char in WILDCARD_CHARS)


def expand_inputs(args: list[str]) -> tuple[list[Path], list[str]]:
    """Expand files and glob patterns while keeping input order stable."""
    paths: list[Path] = []
    errors: list[str] = []
    seen: set[Path] = set()

    for arg in args:
        if has_wildcard(arg):
            # This keeps wildcard behavior the same across PowerShell and Bash.
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


def clamp_score(value: float, max_score: int) -> float:
    """Keep a dimension score inside its legal range."""
    return max(0.0, min(float(max_score), value))


def grade_for(total_score: float) -> str:
    """Convert a total score into A/B/C grade."""
    if total_score >= 80:
        return "A"
    if total_score >= 60:
        return "B"
    return "C"


def progress_bar(score: float, max_score: int, width: int = 20) -> str:
    """Render a simple ASCII progress bar for terminals."""
    ratio = 0.0 if max_score == 0 else score / max_score
    filled = round(width * clamp_score(ratio, 1))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def get_text(data: dict[str, Any], field_name: str) -> str:
    """Read a string field safely."""
    value = data.get(field_name)
    return value if isinstance(value, str) else ""


def score_summary(data: dict[str, Any]) -> DimensionScore:
    """Score summary length and reward technical keywords."""
    summary = get_text(data, "summary").strip()
    length = len(summary)
    lowered_summary = summary.lower()

    if length >= 50:
        base_score = 20
    elif length >= 20:
        base_score = 15
    else:
        base_score = 15 * length / 20

    matched_keywords = sorted(
        keyword for keyword in TECH_KEYWORDS if keyword.lower() in lowered_summary
    )
    keyword_bonus = 5 if matched_keywords else 0
    score = clamp_score(base_score + keyword_bonus, 25)

    if matched_keywords:
        detail = f"{length} chars, keywords: {', '.join(matched_keywords[:5])}"
    else:
        detail = f"{length} chars, no technical keyword bonus"

    return DimensionScore("摘要质量", score, 25, detail)


def score_technical_depth(data: dict[str, Any]) -> DimensionScore:
    """Map article score from 1-10 onto the 0-25 depth scale."""
    raw_score = data.get("score")

    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        return DimensionScore("技术深度", 0, 25, "missing numeric score")

    normalized = clamp_score(raw_score, 10)
    if normalized < 1:
        return DimensionScore("技术深度", 0, 25, "score is below 1")

    # A source score of 1 means minimal depth. A score of 10 means full marks.
    depth_score = (normalized - 1) / 9 * 25
    return DimensionScore(
        "技术深度",
        depth_score,
        25,
        f"source score {raw_score}/10",
    )


def has_timestamp(data: dict[str, Any]) -> bool:
    """Check common top-level and metadata timestamp fields."""
    candidates: list[Any] = []

    for field_name in TIMESTAMP_FIELDS:
        candidates.append(data.get(field_name))

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        for field_name in TIMESTAMP_FIELDS:
            candidates.append(metadata.get(field_name))

    for value in candidates:
        if isinstance(value, str) and DATE_PATTERN.match(value.strip()):
            return True

    return False


def score_format(data: dict[str, Any]) -> DimensionScore:
    """Score five required format signals at four points each."""
    checks = {
        "id": ID_PATTERN.fullmatch(get_text(data, "id")) is not None,
        "title": bool(get_text(data, "title").strip()),
        "source_url": URL_PATTERN.fullmatch(get_text(data, "source_url")) is not None,
        "status": get_text(data, "status") in VALID_STATUSES,
        "timestamp": has_timestamp(data),
    }
    passed = [name for name, is_valid in checks.items() if is_valid]
    missing = [name for name, is_valid in checks.items() if not is_valid]
    score = len(passed) * 4

    if missing:
        detail = f"passed: {', '.join(passed)}; missing: {', '.join(missing)}"
    else:
        detail = "all format checks passed"

    return DimensionScore("格式规范", score, 20, detail)


def score_tags(data: dict[str, Any]) -> DimensionScore:
    """Score tag count and whether tags come from the standard list."""
    tags = data.get("tags")
    if not isinstance(tags, list) or not tags:
        return DimensionScore("标签精度", 0, 15, "missing non-empty tags")

    normalized_tags = [
        tag.strip().lower() for tag in tags if isinstance(tag, str) and tag.strip()
    ]
    if not normalized_tags:
        return DimensionScore("标签精度", 0, 15, "tags must be non-empty strings")

    valid_tags = [tag for tag in normalized_tags if tag in STANDARD_TAGS]
    invalid_tags = [tag for tag in normalized_tags if tag not in STANDARD_TAGS]

    if 1 <= len(normalized_tags) <= 3:
        count_score = 6
    elif len(normalized_tags) <= 5:
        count_score = 4
    else:
        count_score = 2

    legality_score = 9 * len(valid_tags) / len(normalized_tags)
    score = clamp_score(count_score + legality_score, 15)

    if invalid_tags:
        detail = f"valid={len(valid_tags)}, invalid: {', '.join(invalid_tags)}"
    else:
        detail = f"{len(normalized_tags)} standard tags"

    return DimensionScore("标签精度", score, 15, detail)


def score_empty_words(data: dict[str, Any]) -> DimensionScore:
    """Deduct points when vague buzzwords appear in title or summary."""
    text = f"{get_text(data, 'title')} {get_text(data, 'summary')}"
    lowered_text = text.lower()

    zh_hits = [word for word in EMPTY_WORDS_ZH if word in text]
    en_hits = [word for word in EMPTY_WORDS_EN if word in lowered_text]
    hits = sorted(zh_hits + en_hits)

    score = clamp_score(15 - len(hits) * 3, 15)
    if hits:
        detail = f"empty words: {', '.join(hits)}"
    else:
        detail = "no empty words found"

    return DimensionScore("空洞词检测", score, 15, detail)


def build_error_report(file_path: Path, errors: list[str]) -> QualityReport:
    """Create a C-grade report when the file cannot be scored normally."""
    dimensions = [
        DimensionScore("摘要质量", 0, 25, "not scored"),
        DimensionScore("技术深度", 0, 25, "not scored"),
        DimensionScore("格式规范", 0, 20, "not scored"),
        DimensionScore("标签精度", 0, 15, "not scored"),
        DimensionScore("空洞词检测", 0, 15, "not scored"),
    ]
    return QualityReport(file_path, dimensions, 0, "C", errors)


def score_file(file_path: Path) -> QualityReport:
    """Load and score one JSON file."""
    if not file_path.exists():
        return build_error_report(file_path, ["file does not exist"])

    if not file_path.is_file():
        return build_error_report(file_path, ["path is not a file"])

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        return build_error_report(file_path, [f"file is not valid UTF-8: {exc}"])
    except json.JSONDecodeError as exc:
        return build_error_report(
            file_path,
            [f"invalid JSON at line {exc.lineno}, col {exc.colno}"],
        )

    if not isinstance(data, dict):
        return build_error_report(file_path, ["root JSON value must be an object"])

    dimensions = [
        score_summary(data),
        score_technical_depth(data),
        score_format(data),
        score_tags(data),
        score_empty_words(data),
    ]
    total_score = sum(dimension.score for dimension in dimensions)
    grade = grade_for(total_score)

    return QualityReport(file_path, dimensions, total_score, grade, [])


def print_report(report: QualityReport) -> None:
    """Print one quality report with progress bars."""
    print(f"\n{report.path}")
    print(f"Total: {report.total_score:.1f}/100  Grade: {report.grade}")

    for dimension in report.dimensions:
        bar = progress_bar(dimension.score, dimension.max_score)
        print(
            f"  {dimension.name:<10} "
            f"{bar} {dimension.score:>5.1f}/{dimension.max_score} "
            f"- {dimension.detail}"
        )

    for error in report.errors:
        print(f"  error: {error}")


def print_usage() -> None:
    """Print the command format when input is missing."""
    print("Usage: python hooks/check_quality.py <json_file> [json_file2 ...]")


def main(argv: list[str]) -> int:
    """Run quality checks and return a process exit code."""
    # Force UTF-8 so Chinese dimension names render consistently on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if not argv:
        print_usage()
        return 1

    paths, input_errors = expand_inputs(argv)
    reports = [score_file(path) for path in paths]

    for error in input_errors:
        print(f"Input error: {error}")

    for report in reports:
        print_report(report)

    c_grade_count = sum(1 for report in reports if report.grade == "C")
    checked_count = len(reports)
    average_score = (
        sum(report.total_score for report in reports) / checked_count
        if checked_count
        else 0
    )

    print(
        "\nSummary: "
        f"checked={checked_count}, "
        f"average={average_score:.1f}, "
        f"c_grade={c_grade_count}, "
        f"input_errors={len(input_errors)}"
    )

    return 1 if c_grade_count or input_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
