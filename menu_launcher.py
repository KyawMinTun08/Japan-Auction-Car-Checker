"""Start the JACC Telegram bot with the admin command-menu patch loaded."""

import runpy

# Railway virtual environments do not always auto-import usercustomize.py.
# Import it explicitly before bot.py builds Telegram command scopes.
import usercustomize  # noqa: F401

runpy.run_module("bot", run_name="__main__")
