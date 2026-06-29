#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.env_loader import apply_env_file, upsert_env_file
from workflows.feishu_app import list_bot_chats, resolve_feishu_app_config, send_text_message


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load Feishu credentials from .env and discover FEISHU_RECEIVE_ID (chat_id).",
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT_DIR / ".env"),
        help="Path to .env file (default: repository root .env)",
    )
    parser.add_argument("--query", default="", help="Optional group name keyword")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--pick",
        type=int,
        default=0,
        help="Pick the Nth group from the result list (1-based) and write FEISHU_RECEIVE_ID to .env",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write FEISHU_RECEIVE_ID (and FEISHU_RECEIVE_ID_TYPE=chat_id) into .env",
    )
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send a test message using FEISHU_RECEIVE_ID from .env after discovery",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    env_path = Path(args.env_file)
    apply_env_file(env_path)
    config = resolve_feishu_app_config({})

    if not config["app_id"] or not config["app_secret"]:
        print(
            f"Missing FEISHU_APP_ID or FEISHU_APP_SECRET in {env_path}",
            file=sys.stderr,
        )
        return 1

    try:
        chats = list_bot_chats(
            app_id=config["app_id"],
            app_secret=config["app_secret"],
            query=args.query,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to list Feishu chats: {exc}", file=sys.stderr)
        print(
            "\n请确认：\n"
            "1. 应用已发布并安装到企业\n"
            "2. 已开启机器人能力\n"
            "3. 已开通 im:chat / im:chat:readonly 权限\n"
            "4. 应用机器人已被拉进至少一个群",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps({"chats": chats}, ensure_ascii=False, indent=2))
    elif not chats:
        print("没有找到应用机器人所在的群。")
        print("请先把企业自建应用机器人拉进目标飞书群，再重新运行本脚本。")
    else:
        print("应用机器人可见的飞书群：\n")
        for index, chat in enumerate(chats, start=1):
            print(f"{index}. name={chat['name'] or '(未命名)'}")
            print(f"   chat_id={chat['chat_id']}")
            if chat.get("description"):
                print(f"   description={chat['description']}")
            print()
        print("可将某个 chat_id 写入 .env：")
        print("  FEISHU_RECEIVE_ID=<chat_id>")
        print("  FEISHU_RECEIVE_ID_TYPE=chat_id")

    pick_index = args.pick
    if args.write_env:
        if not chats:
            return 1
        if pick_index <= 0:
            if len(chats) == 1:
                pick_index = 1
            else:
                print("发现多个群，请用 --pick N 指定要写入的群序号。", file=sys.stderr)
                return 1
        if pick_index < 1 or pick_index > len(chats):
            print(f"--pick 必须在 1 到 {len(chats)} 之间", file=sys.stderr)
            return 1

        selected = chats[pick_index - 1]
        upsert_env_file(
            env_path,
            {
                "FEISHU_RECEIVE_ID": selected["chat_id"],
                "FEISHU_RECEIVE_ID_TYPE": "chat_id",
            },
        )
        print(f"已写入 {env_path}:")
        print(f"  FEISHU_RECEIVE_ID={selected['chat_id']}")
        print("  FEISHU_RECEIVE_ID_TYPE=chat_id")
        config = resolve_feishu_app_config({})

    if args.send_test:
        if not config["receive_id"]:
            print("FEISHU_RECEIVE_ID 未配置，无法发送测试消息。", file=sys.stderr)
            return 1
        send_text_message(
            app_id=config["app_id"],
            app_secret=config["app_secret"],
            receive_id=config["receive_id"],
            receive_id_type=config["receive_id_type"],
            text="Knowdeage 飞书分发测试：配置成功。",
        )
        print(f"测试消息已发送到 receive_id={config['receive_id']}")

    return 0 if chats else 1


if __name__ == "__main__":
    raise SystemExit(main())
