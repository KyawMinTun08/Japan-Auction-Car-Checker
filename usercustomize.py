"""Telegram command-menu patch for JACC admins.

Python imports ``usercustomize`` automatically after ``sitecustomize``. This
keeps the runtime command handler unchanged and only adds /queue to the private
admin command menu sent to Telegram.
"""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import ExtBot

import legacy_bot as _legacy


_original_set_my_commands = ExtBot.set_my_commands


async def _set_my_commands_with_admin_queue(
    self,
    commands,
    scope=None,
    language_code=None,
    *args,
    **kwargs,
):
    command_list = list(commands)
    if isinstance(scope, BotCommandScopeChat):
        try:
            chat_id = int(scope.chat_id)
        except (TypeError, ValueError):
            chat_id = 0
        if chat_id in _legacy.ADMIN_IDS and not any(
            item.command == "queue" for item in command_list
        ):
            command_list.append(
                BotCommand("queue", "📋 Request Queue ကြည့်ရန် (Admin)")
            )

    return await _original_set_my_commands(
        self,
        command_list,
        scope=scope,
        language_code=language_code,
        *args,
        **kwargs,
    )


ExtBot.set_my_commands = _set_my_commands_with_admin_queue
