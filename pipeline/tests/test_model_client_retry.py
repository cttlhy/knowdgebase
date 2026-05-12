from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from model_client import LLMResponse, Usage, _compute_retry_delay_seconds, chat_with_retry


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


if __name__ == "__main__":
    unittest.main()
