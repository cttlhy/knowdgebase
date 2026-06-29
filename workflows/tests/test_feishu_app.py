from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import workflows.feishu_app as feishu_app_module


class FeishuAppTests(unittest.TestCase):
    def setUp(self) -> None:
        feishu_app_module._token_cache.update({"token": "", "expires_at": 0.0, "app_id": ""})

    def test_get_tenant_access_token_caches_successful_response(self) -> None:
        with patch.object(feishu_app_module.urllib.request, "urlopen") as urlopen_mock:
            response = urlopen_mock.return_value.__enter__.return_value
            response.read.return_value = json.dumps(
                {"code": 0, "tenant_access_token": "t-token", "expire": 7200}
            ).encode("utf-8")
            first = feishu_app_module.get_tenant_access_token("cli_app", "secret")
            second = feishu_app_module.get_tenant_access_token("cli_app", "secret")

        self.assertEqual(first, "t-token")
        self.assertEqual(second, "t-token")
        urlopen_mock.assert_called_once()

    def test_send_text_message_uses_im_api_with_bearer_token(self) -> None:
        seen_urls: list[str] = []

        def fake_urlopen(request: object, timeout: int = 15) -> object:
            url = getattr(request, "full_url", "") or getattr(request, "url", "")
            seen_urls.append(str(url))
            response = urlopen_mock.return_value.__enter__.return_value
            if "tenant_access_token" in str(url):
                response.read.return_value = json.dumps(
                    {"code": 0, "tenant_access_token": "t-token", "expire": 7200}
                ).encode("utf-8")
            else:
                response.read.return_value = json.dumps({"code": 0, "data": {"message_id": "om_1"}}).encode(
                    "utf-8"
                )
            return urlopen_mock.return_value

        with patch.object(feishu_app_module.urllib.request, "urlopen") as urlopen_mock:
            urlopen_mock.side_effect = fake_urlopen
            ok = feishu_app_module.send_text_message(
                app_id="cli_app",
                app_secret="secret",
                receive_id="oc_chat123",
                receive_id_type="chat_id",
                text="hello from kb",
            )

        self.assertTrue(ok)
        self.assertTrue(any("im/v1/messages" in url for url in seen_urls))

    def test_feishu_app_is_configured_requires_all_fields(self) -> None:
        self.assertFalse(
            feishu_app_module.feishu_app_is_configured(
                {"app_id": "cli_app", "app_secret": "secret", "receive_id": ""}
            )
        )
        self.assertTrue(
            feishu_app_module.feishu_app_is_configured(
                {"app_id": "cli_app", "app_secret": "secret", "receive_id": "oc_chat123"}
            )
        )

    def test_list_bot_chats_returns_chat_id_and_name(self) -> None:
        with patch.object(feishu_app_module, "get_tenant_access_token", return_value="t-token"):
            with patch.object(feishu_app_module, "_get_json") as get_json_mock:
                get_json_mock.return_value = {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "chat_id": "oc_group1",
                                "name": "AI 知识库",
                                "description": "daily push",
                                "external": False,
                                "chat_status": "normal",
                            }
                        ],
                        "has_more": False,
                    },
                }
                chats = feishu_app_module.list_bot_chats(app_id="cli_app", app_secret="secret")

        self.assertEqual(chats[0]["chat_id"], "oc_group1")
        self.assertEqual(chats[0]["name"], "AI 知识库")


if __name__ == "__main__":
    unittest.main()
