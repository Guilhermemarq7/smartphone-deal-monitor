from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import requests

API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


@dataclass
class TelegramClient:
    token: str
    timeout: float = 15.0

    def __post_init__(self):
        self.token = (self.token or "").strip()
        if not self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN não configurado")
        self.session = requests.Session()

    def _url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def _check(self, response: requests.Response) -> Any:
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(str(data.get("description") or "Telegram retornou ok=false"))
        return data.get("result")

    def get_me(self) -> dict:
        return self._check(self.session.get(self._url("getMe"), timeout=self.timeout))

    def get_updates(self, limit: int = 100) -> list[dict]:
        return self._check(
            self.session.get(
                self._url("getUpdates"),
                params={"limit": max(1, min(100, int(limit))), "timeout": 0},
                timeout=self.timeout,
            )
        )

    def send_message(self, chat_id: str | int, text: str) -> dict:
        return self._check(
            self.session.post(
                self._url("sendMessage"),
                json={"chat_id": str(chat_id), "text": text},
                timeout=self.timeout,
            )
        )
