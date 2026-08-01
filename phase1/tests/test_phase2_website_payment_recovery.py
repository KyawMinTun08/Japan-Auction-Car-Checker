from pathlib import Path


PATCH = Path("phase2/apps_script_website_payment_patch.gs")


def _source() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_promo_packages_use_canonical_membership_package() -> None:
    source = _source()
    assert "var packageName = jaccPaymentPackage_(row[3]);" in source
    assert "String(row[3] || 'CH').trim().toUpperCase()" not in source


def test_payment_approved_is_the_final_completion_marker() -> None:
    source = _source()
    activation = source.index("var activation = jaccApproveMembershipPayment_({")
    registration = source.index("regSh.getRange(regRow, 5).setValue('APPROVED');", activation)
    payment = source.index("paySh.getRange(payRow, 8).setValue('APPROVED');", registration)
    customer_dm = source.index("JACC Membership Approved", payment)
    assert activation < registration < payment < customer_dm


def test_duplicate_final_approval_repairs_registration_only() -> None:
    source = _source()
    duplicate = source.split("if (approved && currentStatus === 'APPROVED')", 1)[1]
    duplicate = duplicate.split("if (currentStatus !== 'PENDING')", 1)[0]
    assert "regSh.getRange(regRow, 5).setValue('APPROVED')" in duplicate
    assert "jaccApproveMembershipPayment_(" not in duplicate
    assert "duplicate:true" in duplicate
