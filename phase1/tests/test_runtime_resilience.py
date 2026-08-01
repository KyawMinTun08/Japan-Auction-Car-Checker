from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any


PHASE1_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PHASE1_ROOT.parent


def _load_module(name: str, path: Path):
    sys.modules.pop(name, None)
    phase1_path = str(PHASE1_ROOT)
    if phase1_path not in sys.path:
        sys.path.insert(0, phase1_path)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_recovery_worker_marks_successful_delivery_sent(monkeypatch) -> None:
    recovery = _load_module(
        "jacc_test_recovery_success",
        PHASE1_ROOT / "recovery_worker.py",
    )

    class Client:
        def __init__(self) -> None:
            self.sent: list[tuple[str, Any]] = []

        async def mark_sent(self, item_id, result) -> None:
            self.sent.append((item_id, result))

        async def mark_failed(self, item_id, error) -> str:  # pragma: no cover
            raise AssertionError("mark_failed must not run")

    async def fake_deliver(item):
        return recovery.DeliveryResult(
            provider_message_id="123",
            provider_status=200,
            response_excerpt="ok",
        )

    monkeypatch.setattr(recovery, "deliver", fake_deliver)
    client = Client()

    async def scenario() -> None:
        await recovery.process_item(
            client,
            asyncio.Semaphore(1),
            {"id": "outbox-success", "channel": "telegram", "payload": {}},
        )

    asyncio.run(scenario())
    assert len(client.sent) == 1
    assert client.sent[0][0] == "outbox-success"
    assert client.sent[0][1].provider_message_id == "123"


def test_recovery_worker_records_retry_and_dead_letter(monkeypatch) -> None:
    recovery = _load_module(
        "jacc_test_recovery_failure",
        PHASE1_ROOT / "recovery_worker.py",
    )

    class Client:
        def __init__(self, next_status: str) -> None:
            self.next_status = next_status
            self.failed: list[tuple[str, str]] = []

        async def mark_sent(self, item_id, result) -> None:  # pragma: no cover
            raise AssertionError("mark_sent must not run")

        async def mark_failed(self, item_id, error) -> str:
            self.failed.append((item_id, str(error)))
            return self.next_status

    async def failed_delivery(item):
        raise recovery.DeliveryError(
            "controlled failure",
            status_code=503,
            response="temporary outage",
        )

    dead_letters: list[str] = []

    async def fake_dead_letter(item, error) -> None:
        dead_letters.append(str(item["id"]))

    monkeypatch.setattr(recovery, "deliver", failed_delivery)
    monkeypatch.setattr(recovery, "notify_dead_letter", fake_dead_letter)

    async def scenario() -> tuple[Client, Client]:
        retry_client = Client("retrying")
        await recovery.process_item(
            retry_client,
            asyncio.Semaphore(1),
            {"id": "retry-item", "channel": "telegram", "payload": {}},
        )
        dead_client = Client("dead_letter")
        await recovery.process_item(
            dead_client,
            asyncio.Semaphore(1),
            {"id": "dead-item", "channel": "telegram", "payload": {}},
        )
        return retry_client, dead_client

    retry_client, dead_client = asyncio.run(scenario())
    assert retry_client.failed == [("retry-item", "controlled failure")]
    assert dead_client.failed == [("dead-item", "controlled failure")]
    assert dead_letters == ["dead-item"]


def test_recovery_cycle_runs_stuck_recovery_on_schedule() -> None:
    recovery = _load_module(
        "jacc_test_recovery_cycle",
        PHASE1_ROOT / "recovery_worker.py",
    )

    class Client:
        def __init__(self) -> None:
            self.recover_calls = 0
            self.claim_calls = 0

        async def recover_stuck(self):
            self.recover_calls += 1
            return [{"id": "stuck-item"}]

        async def claim(self):
            self.claim_calls += 1
            return []

    client = Client()
    asyncio.run(recovery.run_cycle(client, 20))
    assert client.recover_calls == 1
    assert client.claim_calls == 1


def test_assignment_cycle_handles_expiry_stale_and_no_duplicate_dispatch(monkeypatch) -> None:
    worker = _load_module(
        "jacc_test_assignment_cycle",
        PHASE1_ROOT / "phase1_worker.py",
    )

    class Client:
        async def expire_pending_offers(self):
            return ["request-expired"]

        async def reassign_stale_requests(self):
            return [
                {
                    "request_id": "request-stale",
                    "request_code": "R-STALE",
                    "urgent_auction": False,
                }
            ]

    dispatched: list[str] = []
    admin_events: list[str] = []

    async def fake_dispatch(client, request_id: str) -> None:
        dispatched.append(request_id)

    async def fake_waiting(client):
        return [
            "request-expired",
            "request-stale",
            "request-waiting-1",
            "request-waiting-2",
        ]

    async def fake_notify_admin(client, text, *, request_id, event_key) -> None:
        admin_events.append(event_key)

    monkeypatch.setattr(worker, "dispatch_request", fake_dispatch)
    monkeypatch.setattr(worker, "list_waiting_request_ids", fake_waiting)
    monkeypatch.setattr(worker, "notify_admin", fake_notify_admin)
    monkeypatch.setattr(worker, "PHASE1_SEQUENTIAL_ENABLED", True)

    asyncio.run(worker.run_cycle(Client()))

    assert dispatched == [
        "request-expired",
        "request-stale",
        "request-waiting-1",
        "request-waiting-2",
    ]
    assert admin_events == ["stale-reassign:request-stale"]


def test_ten_request_synthetic_pilot_dispatches_each_request_once(monkeypatch) -> None:
    worker = _load_module(
        "jacc_test_ten_request_pilot",
        PHASE1_ROOT / "phase1_worker.py",
    )

    class Client:
        async def expire_pending_offers(self):
            return []

        async def reassign_stale_requests(self):
            return []

    request_ids = [f"pilot-request-{index:02d}" for index in range(1, 11)]
    dispatched: list[str] = []

    async def fake_waiting(client):
        return list(request_ids)

    async def fake_dispatch(client, request_id: str) -> None:
        dispatched.append(request_id)

    monkeypatch.setattr(worker, "list_waiting_request_ids", fake_waiting)
    monkeypatch.setattr(worker, "dispatch_request", fake_dispatch)
    monkeypatch.setattr(worker, "PHASE1_SEQUENTIAL_ENABLED", True)

    asyncio.run(worker.run_cycle(Client()))
    assert dispatched == request_ids
    assert len(dispatched) == len(set(dispatched)) == 10


def test_restart_recovery_runs_before_telegram_polling() -> None:
    source = (REPO_ROOT / "completion_launcher.py").read_text(encoding="utf-8")
    restore_call = "await _restore_phase1_proxy_sessions()"
    polling_call = "await _legacy.main()"

    assert 'filters={"status": "eq.active"}' in source
    assert "_legacy.proxy_sessions[request_code]" in source
    assert restore_call in source
    assert polling_call in source
    assert source.index(restore_call) < source.index(polling_call)
