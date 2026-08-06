"""Guarded transformer for the owner-supplied current Payment.gs."""

from __future__ import annotations

import argparse
from pathlib import Path


class PaymentScriptPatchError(RuntimeError):
    pass


_MARKER = "return jaccReviewWebsitePayment_(paymentId, approved, adminNote);"
_START = "function jaccReviewPayment_(paymentId, approved, adminNote) {"
_CHECK_OLD = """    telegramId: r[2],
    package: r[3],
    amount: r[4],
    method: r[5],
    slipUrl: r[6],
    status: r[7],
    submittedAt: r[8],
    approvedAt: r[9],
    adminNote: r[10]"""
_CHECK_NEW = """    package: r[3],
    amount: r[4],
    method: r[5],
    status: r[7],
    submittedAt: r[8],
    approvedAt: r[9]"""
_DELEGATE = """function jaccReviewPayment_(paymentId, approved, adminNote) {
  return jaccReviewWebsitePayment_(paymentId, approved, adminNote);
}"""


def _function_end(source: str, start: int) -> int:
    brace = source.find("{", start)
    if brace < 0:
        raise PaymentScriptPatchError("review function body missing")
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
    raise PaymentScriptPatchError("review function is not closed")


def _validate(source: str) -> None:
    if source.count(_MARKER) != 1:
        raise PaymentScriptPatchError("Payment.gs delegate marker missing or duplicated")
    public_check = source.split("function checkPayment", 1)[1].split(
        "function approvePayment", 1
    )[0]
    for field in ("telegramId: r[2]", "slipUrl: r[6]", "adminNote: r[10]"):
        if field in public_check:
            raise PaymentScriptPatchError(f"public checkPayment exposes {field}")


def apply_patch_text(source: str) -> str:
    if _MARKER in source:
        _validate(source)
        return source
    if source.count(_CHECK_OLD) != 1:
        raise PaymentScriptPatchError("checkPayment contract drift")
    if source.count(_START) != 1:
        raise PaymentScriptPatchError("jaccReviewPayment contract drift")

    patched = source.replace(_CHECK_OLD, _CHECK_NEW, 1)
    start = patched.index(_START)
    end = _function_end(patched, start)
    patched = patched[:start] + _DELEGATE + patched[end:]
    _validate(patched)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source = args.path.read_text(encoding="utf-8")
    patched = apply_patch_text(source)
    if args.check:
        if patched != source:
            raise PaymentScriptPatchError("Payment.gs still needs patching")
        print("Apps Script Phase 2 Payment.gs contract: valid")
        return 0

    target = args.output or args.path
    target.write_text(patched, encoding="utf-8")
    print(f"Apps Script Phase 2 Payment.gs candidate written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
