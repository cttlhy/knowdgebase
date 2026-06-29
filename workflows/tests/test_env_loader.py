from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflows.env_loader import apply_env_file, load_env_file, upsert_env_file


class EnvLoaderTests(unittest.TestCase):
    def test_load_env_file_parses_key_value_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\nFEISHU_APP_ID=cli_test\nFEISHU_APP_SECRET=secret\n",
                encoding="utf-8",
            )
            values = load_env_file(path)

        self.assertEqual(values["FEISHU_APP_ID"], "cli_test")
        self.assertEqual(values["FEISHU_APP_SECRET"], "secret")

    def test_upsert_env_file_replaces_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("FEISHU_APP_ID=old\nOTHER=1\n", encoding="utf-8")
            upsert_env_file(path, {"FEISHU_RECEIVE_ID": "oc_new", "FEISHU_RECEIVE_ID_TYPE": "chat_id"})
            values = load_env_file(path)

        self.assertEqual(values["FEISHU_APP_ID"], "old")
        self.assertEqual(values["OTHER"], "1")
        self.assertEqual(values["FEISHU_RECEIVE_ID"], "oc_new")
        self.assertEqual(values["FEISHU_RECEIVE_ID_TYPE"], "chat_id")


if __name__ == "__main__":
    unittest.main()
