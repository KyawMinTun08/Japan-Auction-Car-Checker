from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy_bot.py"
PATCH = ROOT / "membership_approval_patch.py"
HEALTHCHECK = ROOT / "phase1_healthcheck.py"
ADMIN_LAUNCHER = ROOT / "admin_launcher.py"


def test_admin_guards_are_fail_closed_everywhere() -> None:
    """ADMIN_IDS parses to [] on any misconfiguration (bad env var, empty
    string). `if ADMIN_IDS and user_id not in ADMIN_IDS:` short-circuits to
    False when ADMIN_IDS is empty, skipping the guard entirely and letting
    ANY user run admin-only commands including /approve. Every admin check
    must use the fail-closed `if not ADMIN_IDS or ...` form instead."""
    bot = LEGACY.read_text(encoding="utf-8")
    assert 'if ADMIN_IDS and user_id not in ADMIN_IDS:' not in bot
    assert bot.count('if not ADMIN_IDS or user_id not in ADMIN_IDS:') >= 10


def test_broker_double_accept_is_prevented() -> None:
    """Two brokers tapping Accept on the same request within the same event
    loop tick could both win before either write landed. Both the button
    callback and the /accept command must reject a req_id already present
    in proxy_sessions before reserving it."""
    bot = LEGACY.read_text(encoding="utf-8")
    breq_accept = bot[bot.index('elif data.startswith("breq_accept_")'):bot.index("async def approve_member")]
    accept_cmd = bot[bot.index("async def accept_cmd"):bot.index("async def endchat_cmd")]
    assert "req_id in proxy_sessions" in breq_accept
    assert "req_id in proxy_sessions" in accept_cmd


def test_broker_service_type_is_recorded_on_button_accept() -> None:
    """get_broker_session_types() defaults an untagged session to "search",
    which corrupted capacity tracking for auctions accepted via the inline
    button (a broker already full on search could be handed a second
    auction session). The session dict must carry serviceType."""
    bot = LEGACY.read_text(encoding="utf-8")
    breq_accept = bot[bot.index('elif data.startswith("breq_accept_")'):bot.index("async def approve_member")]
    assert 'serviceType' in breq_accept and 'svc_type' in breq_accept


def test_endchat_and_closechat_check_session_ownership() -> None:
    """/endchat, its confirm callback, and /closechat let anyone who knew a
    req_id end or close a chat session that belonged to a different
    customer/broker pair. Each must verify the caller actually owns the
    session before mutating it."""
    bot = LEGACY.read_text(encoding="utf-8")
    endchat_cmd = bot[bot.index("async def endchat_cmd"):bot.index("async def request_timer_task")]
    endchat_yes = bot[bot.index('elif data.startswith("endchat_yes_")'):bot.index('elif data.startswith("breq_accept_")')]
    assert "session.get(\"brokerId\")" in endchat_cmd or 'session.get("brokerId")' in endchat_cmd
    assert 'existing_session.get("brokerId")' in endchat_yes or 'session.get("brokerId")' in endchat_yes
    assert "closer_id not in (str(broker_tg_id), str(customer_id))" in bot


def test_broker_recalc_status_used_instead_of_hard_free() -> None:
    """A broker running both an auction and a search session concurrently
    had the whole record wiped to FREE when only one of the two sessions
    ended (via cancel or the request timer), silently hiding the other
    live session from new requests. Both call sites must recompute status
    from the broker's remaining live sessions."""
    bot = LEGACY.read_text(encoding="utf-8")
    cancelrequest = bot[bot.index("async def cancelrequest_cmd"):bot.index("async def accept_cmd")]
    timer_task = bot[bot.index("async def request_timer_task"):bot.index("def start_request_timer")]
    assert 'status=recalc_broker_status(broker_tg_id)' in cancelrequest
    assert 'status=recalc_broker_status(broker_tg_id)' in timer_task


def test_deposit_confirm_requires_verified_amount_and_dedups_transaction() -> None:
    """dep_ok_ previously confirmed a deposit without checking the OCR'd
    amount actually matched the required 20,000 THB, and without any
    duplicate-transaction protection — a double-tap or a reused slip photo
    could both be confirmed and both trigger a saveDeposit call."""
    bot = LEGACY.read_text(encoding="utf-8")
    dep_ok = bot[bot.index('elif data.startswith("dep_ok_")'):bot.index('elif data.startswith("dep_no_")')]
    assert 'amount_verified' in dep_ok
    assert 'used_deposit_txns' in dep_ok


def test_deposit_second_slip_does_not_silently_overwrite_pending_review() -> None:
    """A member who sends a second slip photo while their first slip is
    still awaiting admin review previously had the first slip's data
    silently overwritten with no warning to either party."""
    bot = LEGACY.read_text(encoding="utf-8")
    assert '"waiting_slip"' in bot
    assert "ပထမ Slip ကို Admin စစ်ဆေးနေဆဲပါ" in bot


def test_auctionwon_validates_price_argument() -> None:
    """int(context.args[1]) crashed the handler with an unhandled
    ValueError on any non-numeric price argument instead of replying with
    a usage message."""
    bot = LEGACY.read_text(encoding="utf-8")
    auctionwon = bot[bot.index("async def auctionwon_cmd"):bot.index("async def refunddone_cmd")]
    assert "except ValueError" in auctionwon


def test_refunddone_checks_deposit_exists_before_claiming_success() -> None:
    """refunddone_cmd called updateDeposit unconditionally before checking
    whether getDeposit found a matching record, so a bad/nonexistent req_id
    still produced a false '✅ Refund ပြီးကြောင်း မှတ်တမ်းတင်ပြီ' message."""
    bot = LEGACY.read_text(encoding="utf-8")
    refunddone = bot[bot.index("async def refunddone_cmd"):bot.index("async def check_expired_members")]
    assert refunddone.index("getDeposit") < refunddone.index("updateDeposit")


def test_price_history_and_add_price_use_normalized_chassis_matching() -> None:
    """PRICE_HISTORY and CARS lookups compared chassis strings with an
    exact/uppercase match, so dash/space format variance (e.g. "ABC-123"
    vs "ABC123") silently produced empty history and duplicate/invisible
    CARS entries. Both must use normalize_chassis_key()."""
    bot = LEGACY.read_text(encoding="utf-8")
    get_price_history = bot[bot.index("def get_price_history"):bot.index("def normalize_year")]
    add_price = bot[bot.index("async def add_price"):bot.index("async def price_history_cmd")]
    assert "normalize_chassis_key(" in get_price_history
    assert "normalize_chassis_key(" in add_price
    assert "CARS.append(car)" in add_price


def test_add_price_rejects_non_positive_price() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    add_price = bot[bot.index("async def add_price"):bot.index("async def price_history_cmd")]
    assert "price <= 0" in add_price


def test_price_history_percent_change_guards_zero_division() -> None:
    """A car's oldest recorded price could legitimately be 0 (a placeholder
    entry); computing percent change against it crashed with
    ZeroDivisionError instead of just omitting the percentage."""
    bot = LEGACY.read_text(encoding="utf-8")
    start = bot.index("async def price_history_cmd")
    end = bot.index("\nasync def ", start + 10)
    price_history_cmd = bot[start:end]
    assert "history[0]['price']" in price_history_cmd or 'history[0]["price"]' in price_history_cmd


def test_editfield_price_updates_price_history_not_dead_car_field() -> None:
    """car["price"] is never read anywhere (PRICE_HISTORY is the real source
    of truth), so the old /editfield price path silently updated a field
    nothing displays. It must call save_price() instead."""
    bot = LEGACY.read_text(encoding="utf-8")
    assert 'car["price"] = new_val' not in bot
    assert "save_price(car['chassis']" in bot


def test_broadcast_requires_admin_confirmation_before_sending() -> None:
    """broadcast_cmd previously sent immediately after resolving targets,
    with no way for the admin to see whether a package filter word (e.g.
    "Web"/"Ch") was silently stripped from the message, or to review the
    final text, before it went out to every matching member."""
    bot = LEGACY.read_text(encoding="utf-8")
    broadcast_cmd = bot[bot.index("async def broadcast_cmd"):bot.index("async def backup_cmd")]
    bcast_send = bot[bot.index('elif data.startswith("bcast_send_")'):bot.index('elif data.startswith("bcast_no_")')]
    bcast_no = bot[bot.index('elif data.startswith("bcast_no_")'):bot.index('elif data.startswith("setqr_")')]
    assert "pending_broadcast_text[user_id]" in broadcast_cmd
    assert "Broadcast Preview" in broadcast_cmd
    assert "pending_broadcast_text" in bcast_send
    assert "pending_broadcast_text" in bcast_no


def test_warned_3days_is_pruned_so_renewals_get_warned_again() -> None:
    """warned_3days was never pruned, so a member who renewed and later
    approached a NEW future expiry was permanently suppressed from ever
    getting another expiry warning for the life of the process."""
    bot = LEGACY.read_text(encoding="utf-8")
    check_expired = bot[bot.index("async def check_expired_members"):]
    assert "warned_3days.discard(uid)" in check_expired


def test_expired_kick_rechecks_status_against_stale_snapshot() -> None:
    """check_expired_members takes one getMembers() snapshot at the top of
    a run and then kicks EXPIRED members in a loop that can run long enough
    for a member to renew mid-loop; without a re-check they were kicked
    anyway based on the stale snapshot."""
    bot = LEGACY.read_text(encoding="utf-8")
    check_expired = bot[bot.index("async def check_expired_members"):]
    assert "fresh_status != \"EXPIRED\"" in check_expired or "fresh_status != 'EXPIRED'" in check_expired


def test_backup_cmd_distinguishes_empty_sheet_from_failure() -> None:
    """A legitimately-empty-but-successful backup (status == 'ok', no csv
    content yet) fell into the generic failure branch and showed a false
    '❌ Backup မရနိုင်ပါ' message."""
    bot = LEGACY.read_text(encoding="utf-8")
    backup_cmd = bot[bot.index("async def backup_cmd"):bot.index("async def finance_cmd")]
    assert 'csv_content.strip()' in backup_cmd


def test_membership_patch_uses_per_member_lock_not_one_global_lock() -> None:
    """A single global asyncio.Lock serialized every admin's approval tap
    for every member behind whichever approval was currently retrying
    (approve_payment_transaction retries for 45-135s), so approving member
    A could block on an unrelated slow retry for member B."""
    patch = PATCH.read_text(encoding="utf-8")
    assert "_approval_lock = asyncio.Lock()" not in patch
    assert "_lock_for_member(" in patch
    assert "_approval_locks: dict[str, asyncio.Lock] = {}" in patch


def test_backupdb_evidence_logging_failure_does_not_orphan_a_sent_backup() -> None:
    """The ZIP and its password were sent to the admin, then a Supabase
    evidence-row write happened; if that write threw, the outer except
    reported '❌ Phase 1 Backup မအောင်မြင်ပါ' even though a real,
    already-delivered, already-passworded ZIP existed — and worse, the
    password send used to happen AFTER the evidence write, so a failure
    there could mean the password was never sent for a ZIP that was."""
    healthcheck = HEALTHCHECK.read_text(encoding="utf-8")
    backupdb_cmd = healthcheck[healthcheck.index("async def backupdb_cmd"):healthcheck.index("def _validate_backup_payload")]
    send_password_pos = backupdb_cmd.index("send_message(chat_id=user_id, text=password)")
    evidence_write_pos = backupdb_cmd.index('_post_row(\n                "jacc_backup_runs"')
    assert send_password_pos < evidence_write_pos
    assert "Evidence မှတ်တမ်း (Supabase) တင်ရာမှာသာ error" in backupdb_cmd


def test_backup_pagination_has_stable_sort_order() -> None:
    """_get_all_rows paged through PostgREST with offset/limit and no order
    clause; concurrent inserts/deletes during a backup run could shift row
    order between pages and silently duplicate or skip rows in the export
    of the one command whose entire purpose is disaster recovery."""
    healthcheck = HEALTHCHECK.read_text(encoding="utf-8")
    get_all_rows = healthcheck[healthcheck.index("async def _get_all_rows"):healthcheck.index("async def _post_row")]
    assert '"order": "id.asc"' in get_all_rows


def test_backupdb_docstring_names_the_correct_railway_entrypoint() -> None:
    healthcheck = HEALTHCHECK.read_text(encoding="utf-8")
    assert "Railway starts ``queue_launcher.py`` directly" not in healthcheck
    assert "phase1_production_launcher.py" in healthcheck


def test_broker_admin_status_change_reports_supabase_sync_failure() -> None:
    """_bot._set_broker_availability (Supabase mirror) ran with no
    try/except after the Google Sheet update already succeeded; a failure
    there left the two systems out of sync with no admin feedback at all
    (the success reply never sent, no error shown either)."""
    admin_launcher = ADMIN_LAUNCHER.read_text(encoding="utf-8")
    assert "supabase_synced = True" in admin_launcher
    assert "supabase_synced = False" in admin_launcher
    assert "Supabase sync မအောင်မြင်ပါ" in admin_launcher
