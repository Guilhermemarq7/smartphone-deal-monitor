from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from src.telegram import TelegramClient


def main() -> int:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("ERRO: TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID precisam estar configurados.")
        return 2
    try:
        client = TelegramClient(token)
        me = client.get_me()
        client.send_message(chat_id, "✅ GitHub Actions/Radar: teste do Telegram concluído com sucesso.")
        print(f"Telegram OK: @{me.get('username','?')} -> chat {chat_id}")
        return 0
    except Exception as exc:
        print(f"ERRO Telegram: {type(exc).__name__}: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
