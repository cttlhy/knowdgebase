from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from workflows.env_loader import apply_env_file
from workflows.feishu_app import list_bot_chats, resolve_feishu_app_config, send_text_message

ROOT_DIR = Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover Feishu group chat_id values for FEISHU_RECEIVE_ID configuration.",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="Optional .env file path; loaded before reading Feishu credentials",
    )
    parser.add_argument("--query", default="", help="Optional group name keyword search")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a human-readable table",
    )
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send a test message when FEISHU_RECEIVE_ID is already configured",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.env_file:
        apply_env_file(Path(args.env_file))
    elif (ROOT_DIR / ".env").exists():
        apply_env_file(ROOT_DIR / ".env")
    config = resolve_feishu_app_config({})

    if not config["app_id"] or not config["app_secret"]:
        print(
            "Missing FEISHU_APP_ID or FEISHU_APP_SECRET.\n"
            "Set them in environment variables or GitHub Actions secrets first.",
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
            "\nChecklist:\n"
            "1. App is published and installed in your tenant\n"
            "2. Bot capability is enabled\n"
            "3. Permission im:chat or im:chat:readonly is granted\n"
            "4. The app bot has been added to at least one group",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps({"chats": chats}, ensure_ascii=False, indent=2))
    else:
        if not chats:
            print("No group chats found for this app bot.")
            print("Add the app bot to a Feishu group, then run this command again.")
        else:
            print("Feishu groups visible to your app bot:\n")
            for index, chat in enumerate(chats, start=1):
                print(f"{index}. name={chat['name'] or '(no name)'}")
                print(f"   chat_id={chat['chat_id']}")
                if chat.get("description"):
                    print(f"   description={chat['description']}")
                print()
            print("Next step:")
            print("Add one chat_id to GitHub Secrets as FEISHU_RECEIVE_ID")
            print("Optional: set FEISHU_RECEIVE_ID_TYPE=chat_id (default)")

    if args.send_test:
        if not config["receive_id"]:
            print("FEISHU_RECEIVE_ID is not configured; skip test message.", file=sys.stderr)
            return 1
        send_text_message(
            app_id=config["app_id"],
            app_secret=config["app_secret"],
            receive_id=config["receive_id"],
            receive_id_type=config["receive_id_type"],
            text="Knowdeage 飞书分发测试：配置成功。",
        )
        print(f"Test message sent to receive_id={config['receive_id']}")

    return 0 if chats or args.send_test else 1


if __name__ == "__main__":
    raise SystemExit(main())
