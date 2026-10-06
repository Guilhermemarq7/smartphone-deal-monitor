from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.getenv(k, "").strip()]
    if missing:
        print("ERRO: GitHub Actions está configurado para Telegram, mas faltam secrets:")
        for key in missing:
            print(" - " + key)
        print("Crie-os em Settings > Secrets and variables > Actions > New repository secret.")
        return 2
    Path("data").mkdir(exist_ok=True)
    print("Cloud preflight OK. Secrets obrigatórios presentes; diretório de estado pronto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
