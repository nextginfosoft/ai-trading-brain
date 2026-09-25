"""Telegram command bot access control when bound to a group chat."""

import os

import dotenv
import pytest

# Importing the bot pulls in config.py, which load_dotenv()s the developer's .env
# into os.environ at import time. Snapshot and restore so it can't leak into
# other tests (e.g. tests/unit/configuration read IIOS_ENV).
_env_before = dict(os.environ)
from notifications.telegram_bot import TelegramCommandBot  # noqa: E402
os.environ.clear()
os.environ.update(_env_before)

GROUP_ID = "-1001234567890"
ADMIN_ID = "111"
MEMBER_ID = "222"


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    # TelegramCommandBot.__init__ calls load_dotenv(); keep the developer's .env
    # out of os.environ so it can't leak into other tests.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", GROUP_ID)
    monkeypatch.setenv("TELEGRAM_WHITELIST_IDS", ADMIN_ID)
    b = TelegramCommandBot()
    b.sent = []
    b._send = lambda chat_id, text, parse_mode="HTML": b.sent.append((chat_id, text))
    b.ran = []
    for cmd in ("/pause", "/resume", "/token", "/rescan", "/status", "/pnl"):
        b._handlers[cmd] = lambda msg, cmd=cmd: b.ran.append(cmd) or f"ran {cmd}"
    return b


def update(text, chat_id, chat_type, user_id):
    return {"message": {"text": text, "chat": {"id": int(chat_id), "type": chat_type},
                        "from": {"id": int(user_id), "first_name": "T"}}}


def test_group_member_can_use_read_only_commands(bot):
    bot._handle_update(update("/status", GROUP_ID, "supergroup", MEMBER_ID))
    bot._handle_update(update("/pnl@TradeSenseAI_bot", GROUP_ID, "supergroup", MEMBER_ID))
    assert bot.ran == ["/status", "/pnl"]


@pytest.mark.parametrize("cmd", ["/pause", "/resume", "/rescan"])
def test_group_member_cannot_run_control_commands(bot, cmd):
    bot._handle_update(update(cmd, GROUP_ID, "supergroup", MEMBER_ID))
    assert bot.ran == []
    assert "restricted to administrators" in bot.sent[-1][1]


def test_admin_can_run_control_commands_in_group(bot):
    bot._handle_update(update("/pause", GROUP_ID, "supergroup", ADMIN_ID))
    bot._handle_update(update("/resume", GROUP_ID, "supergroup", ADMIN_ID))
    assert bot.ran == ["/pause", "/resume"]


def test_token_refused_in_group_even_for_admin(bot):
    bot._handle_update(update("/token abc", GROUP_ID, "supergroup", ADMIN_ID))
    assert bot.ran == []
    assert "private chat" in bot.sent[-1][1]


def test_admin_can_dm_bot_including_token(bot):
    bot._handle_update(update("/token abc", ADMIN_ID, "private", ADMIN_ID))
    bot._handle_update(update("/status", ADMIN_ID, "private", ADMIN_ID))
    assert bot.ran == ["/token", "/status"]
    assert all(chat == ADMIN_ID for chat, _ in bot.sent)


def test_stranger_dm_is_rejected(bot):
    bot._handle_update(update("/status", MEMBER_ID, "private", MEMBER_ID))
    assert bot.ran == []
    assert "Unauthorized" in bot.sent[-1][1]


def _kite_bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", GROUP_ID)
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "https://dash.example")
    b = TelegramCommandBot()
    b.pushed = []
    b.push = lambda text, parse_mode="HTML": b.pushed.append(text)
    return b


def test_kite_startup_message_reflects_connection(monkeypatch):
    b = _kite_bot(monkeypatch)
    assert b._kite_reminders(False, False, "", "", "2026-09-28", 0, 7, 0)[0] is True
    assert "not connected" in b.pushed[-1] and "https://dash.example" in b.pushed[-1]
    b._kite_reminders(True, False, "", "", "2026-09-28", 0, 7, 0)
    assert "connected" in b.pushed[-1] and "not connected" not in b.pushed[-1]


def test_kite_morning_reminder_once_per_weekday_only_when_disconnected(monkeypatch):
    b = _kite_bot(monkeypatch)
    state = b._kite_reminders(False, True, "", "", "2026-09-28", 0, 8, 31)   # Monday 08:31
    assert len(b.pushed) == 1 and "Zerodha login needed" in b.pushed[0]
    b._kite_reminders(False, *state, "2026-09-28", 0, 8, 35)                   # same day: no repeat
    b._kite_reminders(True, True, "", "", "2026-09-29", 1, 8, 31)             # connected: silent
    b._kite_reminders(False, True, "", "", "2026-10-03", 5, 8, 31)            # Saturday: silent
    assert len(b.pushed) == 1
    b._kite_reminders(False, True, "2026-09-28", "", "2026-09-28", 0, 9, 16)  # 09:15 nudge
    assert "Market is OPEN" in b.pushed[-1]


def test_private_owner_setup_still_works(monkeypatch):
    """Legacy: bot bound to the owner's private chat, no whitelist configured."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", ADMIN_ID)
    monkeypatch.setenv("TELEGRAM_WHITELIST_IDS", "")
    b = TelegramCommandBot()
    ran = []
    b._send = lambda *a, **k: None
    b._handlers["/pause"] = lambda msg: ran.append("/pause") or "ok"
    b._handle_update(update("/pause", ADMIN_ID, "private", ADMIN_ID))
    assert ran == ["/pause"]
