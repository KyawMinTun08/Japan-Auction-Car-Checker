"""JACC bot launcher with a safe Phase 1 request mirror bridge.

The original production bot implementation is kept in ``legacy_bot.py``.
This launcher wraps only ``submit_request`` so the current Google Sheets and
broker broadcast flow continues while requests are also mirrored to Supabase.
"""

import asyncio
import traceback

import legacy_bot as _legacy
from legacy_bot import *  # noqa: F401,F403 - preserve existing import surface


_original_submit_request = _legacy.submit_request


async def submit_request(context, user_id: int, username: str):
    """Mirror the pending request to Phase 1, then run the legacy flow."""
    req = _legacy.pending_request.get(user_id)

    if req and _legacy.phase1 is not None:
        data = dict(req.get("data") or {})
        try:
            phase1_request = (
                await _legacy.phase1.create_request_for_telegram_customer(
                    telegram_user_id=user_id,
                    service_type=(
                        "auction"
                        if data.get("service_type") == "auction"
                        else "outside_car"
                    ),
                    form_data={
                        "username": username,
                        "car_name": data.get("car_name", ""),
                        "year": data.get("year", ""),
                        "grade": data.get("grade", ""),
                        "budget": data.get("budget", ""),
                        "condition": data.get("condition", ""),
                        "timeline": data.get("timeline", ""),
                    },
                )
            )
            _legacy.logger.info(
                "Phase 1 request mirrored: %s",
                phase1_request.get("request_code"),
            )
        except _legacy.JaccPhase1Error as exc:
            _legacy.logger.warning(
                "Phase 1 request mirror skipped: %s",
                exc,
            )
        except Exception:
            _legacy.logger.exception("Phase 1 request mirror failed")

    await _original_submit_request(context, user_id, username)


# Functions defined in legacy_bot resolve this global at runtime, so replacing
# it here integrates the bridge without rewriting the large production file.
_legacy.submit_request = submit_request


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
