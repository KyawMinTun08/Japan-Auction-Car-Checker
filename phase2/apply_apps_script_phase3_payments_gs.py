"""Guarded transformer for the owner-supplied current Phase3Payments.gs."""

from __future__ import annotations

import argparse
from pathlib import Path


class Phase3PaymentPatchError(RuntimeError):
    """Raised when Phase3Payments.gs no longer matches the reviewed contract."""


_REPLACEMENTS = {
    "function submitWebPayment_(body) {": """function submitWebPayment_(body) {
  return jaccSubmitPhase3WebPayment_(body);
}""",
    "function getWebPaymentStatus_(paymentId, userId) {": """function getWebPaymentStatus_(paymentId, userId) {
  return jaccGetPhase3WebPaymentStatus_(paymentId, userId);
}""",
    "function approveWebPayment_(paymentId, adminId) {": """function approveWebPayment_(paymentId, adminId) {
  return jaccReviewPhase3WebPayment_(paymentId, true, adminId, "");
}""",
    "function rejectWebPayment_(paymentId, adminId, reason) {": """function rejectWebPayment_(paymentId, adminId, reason) {
  return jaccReviewPhase3WebPayment_(paymentId, false, adminId, reason);
}""",
}

_MARKER = "return jaccSubmitPhase3WebPayment_(body);"


def _function_end(source: str, start: int) -> int:
    brace = source.find("{", start)
    if brace < 0:
        raise Phase3PaymentPatchError("function body missing")

    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    i = brace

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1

    raise Phase3PaymentPatchError("function is not closed")


def _replace_function(source: str, signature: str, replacement: str) -> str:
    count = source.count(signature)
    if count != 1:
        raise Phase3PaymentPatchError(
            f"{signature} contract drift: expected one function, found {count}"
        )
    start = source.index(signature)
    end = _function_end(source, start)
    return source[:start] + replacement + source[end:]


def _validate(source: str) -> None:
    required = (
        "return jaccSubmitPhase3WebPayment_(body);",
        "return jaccGetPhase3WebPaymentStatus_(paymentId, userId);",
        'return jaccReviewPhase3WebPayment_(paymentId, true, adminId, "");',
        "return jaccReviewPhase3WebPayment_(paymentId, false, adminId, reason);",
        "function handlePhase3PaymentAction_(body)",
        "function getPaymentSheet_()",
        "function savePaymentSlip_(paymentId, dataUrl, mimeType)",
        "function notifyPaymentAdmin_(payment)",
        "function sendPaymentTelegramMessage_(chatId, text)",
    )
    for marker in required:
        if marker not in source:
            raise Phase3PaymentPatchError(f"patched source missing marker: {marker}")

    protected_region = source.split("function submitWebPayment_", 1)[1].split(
        "function getPaymentSheet_", 1
    )[0]
    forbidden = (
        "saveMember(",
        "password: password",
        "slipUrl: slipUrl",
        "generateWebPassword_();",
    )
    for marker in forbidden:
        if marker in protected_region:
            raise Phase3PaymentPatchError(f"legacy Phase 3 approval remains: {marker}")


def apply_patch_text(source: str) -> str:
    """Return the reviewed Phase 2 Phase3Payments.gs candidate."""

    if _MARKER in source:
        _validate(source)
        return source

    patched = source
    for signature, replacement in _REPLACEMENTS.items():
        patched = _replace_function(patched, signature, replacement)

    _validate(patched)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Current Phase3Payments.gs source")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source = args.path.read_text(encoding="utf-8")
    patched = apply_patch_text(source)

    if args.check:
        if patched != source:
            raise Phase3PaymentPatchError("Phase3Payments.gs still needs patching")
        print("Apps Script Phase 2 Phase3Payments.gs contract: valid")
        return 0

    target = args.output or args.path
    target.write_text(patched, encoding="utf-8")
    print(f"Apps Script Phase 2 Phase3Payments.gs candidate written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
