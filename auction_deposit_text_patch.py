"""Ensure all legacy Telegram convenience-message paths show the MMK auction deposit.

The main deposit policy patch already replaces the deposit business logic.  Some
legacy screens are emitted through Message.reply_text / Message.edit_text /
CallbackQuery.edit_message_text rather than ExtBot.send_message directly, so
this lightweight patch normalises only the old fixed deposit label there.
"""

from __future__ import annotations

import os
from typing import Any

from telegram import CallbackQuery, Message


_DEPOSIT_MMK = int(os.environ.get("AUCTION_DEPOSIT_MMK", "1000000"))


def _policy_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.replace("฿20,000", f"{_DEPOSIT_MMK:,} ကျပ်")


if not getattr(Message, "_jacc_mmk_deposit_text_wrapped", False):
    _orig_reply_text = Message.reply_text
    _orig_edit_text = Message.edit_text

    async def _reply_text(self, text, *args, **kwargs):
        return await _orig_reply_text(self, _policy_text(text), *args, **kwargs)

    async def _edit_text(self, text, *args, **kwargs):
        return await _orig_edit_text(self, _policy_text(text), *args, **kwargs)

    Message.reply_text = _reply_text
    Message.edit_text = _edit_text
    Message._jacc_mmk_deposit_text_wrapped = True


if not getattr(CallbackQuery, "_jacc_mmk_deposit_text_wrapped", False):
    _orig_callback_edit_message_text = CallbackQuery.edit_message_text

    async def _callback_edit_message_text(self, text, *args, **kwargs):
        return await _orig_callback_edit_message_text(
            self,
            _policy_text(text),
            *args,
            **kwargs,
        )

    CallbackQuery.edit_message_text = _callback_edit_message_text
    CallbackQuery._jacc_mmk_deposit_text_wrapped = True
