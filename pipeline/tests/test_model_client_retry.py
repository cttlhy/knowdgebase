from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import httpx

from model_client import (
    CostTracker,
    LLMResponse,
    OpenAICompatibleProvider,
    ProviderConfig,
    Usage,
    _compute_retry_delay_seconds,
    chat_with_retry,
)


class SequenceProvider:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        outcome = self._outcomes[self.calls - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def build_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(
        message=f"status={status_code}",
        request=request,
        response=response,
    )


class ChatWithRetryTests(unittest.TestCase):
    def test_retry_on_500_then_success(self) -> None:
        provider = SequenceProvider(
            [
                build_http_status_error(500),
                build_http_status_error(502),
                LLMResponse(content="ok", usage=Usage(1, 1, 2)),
            ]
        )
        with patch("model_client.time.sleep") as sleep_mock:
            response = chat_with_retry(
                provider=provider,
                messages=[{"role": "user", "content": "hello"}],
                max_retries=3,
                base_delay_seconds=1.0,
                max_delay_seconds=20.0,
                jitter_min=1.0,
                jitter_max=1.0,
                item_title="demo",
                item_url="https://example.com/item",
            )
        self.assertEqual(response.content, "ok")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1.0, 2.0])

    def test_no_retry_on_400(self) -> None:
        provider = SequenceProvider([build_http_status_error(400)])
        with patch("model_client.time.sleep") as sleep_mock:
            with self.assertRaises(httpx.HTTPStatusError):
                chat_with_retry(
                    provider=provider,
                    messages=[{"role": "user", "content": "hello"}],
                    max_retries=3,
                )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(sleep_mock.call_count, 0)

    def test_retry_on_429_then_success(self) -> None:
        provider = SequenceProvider(
            [
                build_http_status_error(429),
                LLMResponse(content="ok", usage=Usage(1, 1, 2)),
            ]
        )
        with patch("model_client.time.sleep") as sleep_mock:
            response = chat_with_retry(
                provider=provider,
                messages=[{"role": "user", "content": "hello"}],
                max_retries=3,
                jitter_min=1.0,
                jitter_max=1.0,
            )
        self.assertEqual(response.content, "ok")
        self.assertEqual(provider.calls, 2)
        self.assertEqual(sleep_mock.call_count, 1)
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 1.0)

    def test_retry_on_timeout_then_success(self) -> None:
        provider = SequenceProvider(
            [
                httpx.ReadTimeout("timeout", request=httpx.Request("POST", "https://example.com/chat/completions")),
                LLMResponse(content="ok", usage=Usage(1, 1, 2)),
            ]
        )
        with patch("model_client.time.sleep") as sleep_mock:
            response = chat_with_retry(
                provider=provider,
                messages=[{"role": "user", "content": "hello"}],
                max_retries=3,
                jitter_min=1.0,
                jitter_max=1.0,
            )
        self.assertEqual(response.content, "ok")
        self.assertEqual(provider.calls, 2)
        self.assertEqual(sleep_mock.call_count, 1)

    def test_log_missing_title_and_url_fallback(self) -> None:
        provider = SequenceProvider([build_http_status_error(400)])
        with patch("model_client.time.sleep") as sleep_mock:
            with self.assertLogs("model_client", level="ERROR") as logs:
                with self.assertRaises(httpx.HTTPStatusError):
                    chat_with_retry(
                        provider=provider,
                        messages=[{"role": "user", "content": "hello"}],
                        max_retries=3,
                        item_title="",
                        item_url="",
                    )
        self.assertEqual(sleep_mock.call_count, 0)
        joined_logs = "\n".join(logs.output)
        self.assertIn("title=<missing>", joined_logs)
        self.assertIn("url=<missing>", joined_logs)

    def test_jitter_never_reduces_delay(self) -> None:
        delay = _compute_retry_delay_seconds(
            attempt=2,
            base_delay_seconds=1.0,
            max_delay_seconds=20.0,
            jitter_min=1.0,
            jitter_max=1.5,
            random_fn=lambda _min, _max: 0.1,
        )
        self.assertGreaterEqual(delay, 2.0)


class CostTrackerTests(unittest.TestCase):
    def test_estimated_cost_uses_rmb_per_million_pricing(self) -> None:
        tracker = CostTracker()
        tracker.record(
            usage=Usage(prompt_tokens=1_000_000, completion_tokens=500_000, total_tokens=1_500_000),
            provider="deepseek",
        )
        self.assertEqual(tracker.estimated_cost("deepseek"), 2.0)

    def test_report_prints_summary(self) -> None:
        tracker = CostTracker()
        tracker.record(
            usage=Usage(prompt_tokens=250_000, completion_tokens=250_000, total_tokens=500_000),
            provider="qwen",
        )

        stream = io.StringIO()
        with redirect_stdout(stream):
            tracker.report("qwen")

        output = stream.getvalue()
        self.assertIn("provider=qwen", output)
        self.assertIn("estimated_cost_rmb=4.000000", output)

    def test_provider_chat_records_usage_automatically(self) -> None:
        provider = OpenAICompatibleProvider(
            ProviderConfig(
                provider_name="deepseek",
                api_key="test-key",
                base_url="https://example.com/v1",
                model="deepseek-chat",
            )
        )
        payload = {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }
        response = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com/v1/chat/completions"),
            json=payload,
        )

        tracker = CostTracker()
        with patch("model_client.tracker", tracker):
            with patch("model_client.httpx.Client") as client_cls:
                client = client_cls.return_value.__enter__.return_value
                client.post.return_value = response

                provider.chat(messages=[{"role": "user", "content": "hello"}])

        self.assertEqual(tracker.estimated_cost("deepseek"), 0.0002)


if __name__ == "__main__":
    unittest.main()
