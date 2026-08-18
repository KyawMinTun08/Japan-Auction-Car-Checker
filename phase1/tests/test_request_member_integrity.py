from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE_GS = (ROOT / "Code.gs").read_text(encoding="utf-8")
LEGACY_BOT = (ROOT / "legacy_bot.py").read_text(encoding="utf-8")


def test_requests_schema_and_server_mapping_helpers_exist():
    expected = [
        '"ReqID","CustomerID","Username","CarType"',
        '"Timeline","Status","BrokerID","CreatedDate"',
        "function _normalizeRequestId_(value)",
        "function _validRequestId_(value)",
        "function _requestIdExists_(sheet, reqId)",
        "function _newRequestId_(sheet, prefix)",
    ]
    for marker in expected:
        assert marker in CODE_GS, marker


def test_add_request_requires_owner_and_returns_authoritative_identity():
    assert 'msg:"customer_id_required"' in CODE_GS
    assert 'msg:"username_required"' in CODE_GS
    assert 'var requestPrefix = String(ar.carType || "").trim().toUpperCase() === "AUCTION" ? "A" : "R";' in CODE_GS
    assert 'var storedReqId = requestedReqId || _newRequestId_(arSheet, requestPrefix);' in CODE_GS
    assert 'reqId:storedReqId, customerId:arCustomerId, username:arUsername' in CODE_GS
    assert 'requestIdRegenerated:requestIdRegenerated' in CODE_GS


def test_request_id_duplicates_are_regenerated_and_updates_can_check_owner():
    assert 'if (requestedReqId && _requestIdExists_(arSheet, requestedReqId))' in CODE_GS
    assert 'requestIdRegenerated = true' in CODE_GS
    assert 'msg:"request_owner_mismatch"' in CODE_GS
    assert 'var urOwnerId = String(data.customerId || "").trim()' in CODE_GS
    assert 'var grOwnerId = String(data.customerId || "").trim()' in CODE_GS


def test_web_status_filters_by_customer_id():
    assert "const uid = String(payload.customerId || '');" in CODE_GS
    assert "if (String(rows[i][1]) === uid) {" in CODE_GS
    assert "return _json({status:'ok', requests: results.reverse()});" in CODE_GS


def test_bot_uses_backend_request_id_and_restores_failed_request():
    assert 'request_resp = await client.post(SHEET_WEBHOOK' in LEGACY_BOT
    assert 'request_resp.raise_for_status()' in LEGACY_BOT
    assert 'request_result = request_resp.json()' in LEGACY_BOT
    assert 'req_id = str(request_result.get("reqId") or req_id)' in LEGACY_BOT
    assert 'pending_request[user_id] = req' in LEGACY_BOT
    assert 'Request ID/Member ID' in LEGACY_BOT
