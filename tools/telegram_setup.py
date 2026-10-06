from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from src.telegram import TelegramClient, TelegramError

ENV_PATH = Path(".env")


def upsert_env(key: str, value: str):
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = text.splitlines()
    found = False
    out = []
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("ERRO: TELEGRAM_BOT_TOKEN está vazio.")
        print("1) Copie .env.example para .env")
        print("2) Cole no .env o token que o @BotFather entregou")
        print("3) Execute este comando novamente")
        return 2
    try:
        client = TelegramClient(token)
        me = client.get_me()
        print(f"Bot conectado: @{me.get('username','?')} ({me.get('first_name','bot')})")
        print("Buscando a conversa privada mais recente...")
        updates = client.get_updates(100)
    except Exception as exc:
        print(f"ERRO ao falar com o Telegram: {type(exc).__name__}: {exc}")
        return 3

    candidates = []
    for update in updates:
        msg = update.get("message") or update.get("edited_message")
        if not isinstance(msg, dict):
            continue
        chat = msg.get("chat") or {}
        if chat.get("type") != "private" or chat.get("id") is None:
            continue
        candidates.append((int(update.get("update_id", 0)), chat, msg))

    if not candidates:
        print("Nenhuma conversa privada encontrada.")
        print("Abra o bot no Telegram, toque em START/INICIAR ou mande /start, e rode este comando de novo.")
        print("Observação: updates do Bot API não ficam disponíveis indefinidamente; faça isso logo após enviar /start.")
        return 4

    _, chat, msg = max(candidates, key=lambda x: x[0])
    chat_id = str(chat["id"])
    who = " ".join(x for x in [chat.get("first_name"), chat.get("last_name")] if x) or chat.get("username") or "usuário"
    print(f"Conversa encontrada: {who}")
    print(f"CHAT_ID: {chat_id}")
    upsert_env("TELEGRAM_CHAT_ID", chat_id)
    print("TELEGRAM_CHAT_ID gravado no arquivo .env local.")
    try:
        client.send_message(chat_id, "✅ Radar de celulares conectado ao Telegram. Se você recebeu isto, a integração local está funcionando.")
        print("Mensagem de teste enviada com sucesso.")
    except Exception as exc:
        print(f"CHAT_ID salvo, mas o envio de teste falhou: {type(exc).__name__}: {exc}")
        return 5
    print("\nIMPORTANTE: não envie seu token para ninguém e não faça commit do arquivo .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
