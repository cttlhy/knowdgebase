from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

try:
    from pipeline.model_client import chat
except ModuleNotFoundError:
    # 支持直接运行 `python patterns/supervisor.py`。
    # 直接运行脚本时，Python 只会把 patterns 目录加入 sys.path，
    # 这里把项目根目录补进去，这样可以导入同级的 pipeline 包。
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    project_root_str = str(PROJECT_ROOT)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    from pipeline.model_client import chat

LOGGER = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse model text into JSON object with a small fallback."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Model returned empty content.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Model response does not contain JSON object.") from None
        data = json.loads(raw[start : end + 1])

    if not isinstance(data, dict):
        raise ValueError("Model JSON must be an object.")
    return data


def _worker_prompt(task: str, feedback: str | None) -> str:
    # Keep the worker output predictable so supervisor can score it.
    base = (
        "请分析下面任务，并仅输出 JSON 对象。\n"
        "建议字段：summary(字符串), key_points(字符串列表), risks(字符串列表), next_steps(字符串列表)。\n"
        "不要输出 Markdown，不要输出解释。\n"
        f"任务：{task}"
    )
    if not feedback:
        return base
    return f"{base}\n\n上一轮反馈：{feedback}\n请根据反馈改进后重新输出 JSON。"


def _review_prompt(task: str, worker_output: dict[str, Any]) -> str:
    # Require strict machine-readable output for deterministic loop control.
    return (
        "你是质量审核员。请审核 worker 的 JSON 分析报告。\n"
        "评分维度：准确性(1-10)、深度(1-10)、格式(1-10)。\n"
        "请先打三项分，再给一个综合 score(1-10，取三项平均后四舍五入)。\n"
        "通过规则：score >= 7 才 passed=true，否则 passed=false。\n"
        "仅输出 JSON，格式必须是："
        '{"passed": bool, "score": int, "feedback": str}。\n'
        "feedback 要具体、可执行。\n"
        f"任务：{task}\n"
        f"worker 输出：{json.dumps(worker_output, ensure_ascii=False)}"
    )


def supervisor(task: str, max_retries: int = 3) -> dict[str, Any]:
    """Run worker-supervisor loop and return final decision payload."""
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    clean_task = str(task or "").strip()
    if not clean_task:
        raise ValueError("task must not be empty")

    feedback: str | None = None
    latest_output: dict[str, Any] | None = None
    final_score = 0

    for attempt in range(1, max_retries + 1):
        worker_text, _ = chat(
            messages=[
                {"role": "system", "content": "你是 Worker Agent。你只输出 JSON。"},
                {"role": "user", "content": _worker_prompt(clean_task, feedback)},
            ],
            temperature=0.2,
        )
        latest_output = _extract_json_object(worker_text)

        review_text, _ = chat(
            messages=[
                {"role": "system", "content": "你是 Supervisor Agent。你只输出 JSON。"},
                {"role": "user", "content": _review_prompt(clean_task, latest_output)},
            ],
            temperature=0.0,
        )
        review = _extract_json_object(review_text)
        passed = bool(review.get("passed", False))
        final_score = int(review.get("score", 0))
        feedback = str(review.get("feedback", "")).strip() or "请提高准确性、深度和格式一致性。"

        if passed and final_score >= 7:
            return {
                "output": latest_output,
                "attempts": attempt,
                "final_score": final_score,
            }

    LOGGER.warning("Supervisor reached retry limit. Returning latest output with warning.")
    return {
        "output": latest_output or {},
        "attempts": max_retries,
        "final_score": final_score,
        "warning": f"超过最大重试次数({max_retries})，返回最后一轮结果。",
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    demo_task = "请分析某 AI 开源项目的技术价值与落地风险。"
    try:
        result = supervisor(demo_task, max_retries=3)
        LOGGER.info("Supervisor result: %s", json.dumps(result, ensure_ascii=False))
    except Exception:
        LOGGER.exception("Supervisor demo run failed.")
