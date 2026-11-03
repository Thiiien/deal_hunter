import logging

import httpx

from .config import Config

log = logging.getLogger(__name__)

_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


class Notifier:
    """Sends messages to Telegram. Silently no-ops when token/chat_id is unset."""

    def __init__(self, config: Config):
        self._token = config.telegram_token
        self._admin_id = config.admin_chat_id
        self._channel_id = config.telegram_channel_id

    def alert_admin(self, text: str, reply_markup: dict | None = None) -> int | None:
        return self._send(self._admin_id, text, reply_markup=reply_markup)

    def broadcast_deal(self, text: str, reply_markup: dict | None = None) -> int | None:
        return self._send(self._channel_id, text, reply_markup=reply_markup)

    def edit_admin_message(self, message_id: int, text: str, reply_markup: dict | None = None):
        if not self._token or not self._admin_id or not message_id:
            return
        url = _TG_BASE.format(token=self._token, method="editMessageText")
        payload: dict = {
            "chat_id": self._admin_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            httpx.post(url, json=payload, timeout=15)
        except Exception as exc:
            log.warning("Telegram editMessageText failed: %s", exc)

    def _send(self, chat_id: str, text: str, reply_markup: dict | None = None) -> int | None:
        if not self._token or not chat_id:
            return None
        url = _TG_BASE.format(token=self._token, method="sendMessage")
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = httpx.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("ok") and "result" in data:
                    return data["result"].get("message_id")
        except Exception as exc:
            log.warning("Telegram send failed: %s", exc)
        return None
