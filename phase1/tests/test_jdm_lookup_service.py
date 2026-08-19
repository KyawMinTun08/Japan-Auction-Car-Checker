import asyncio

from jdm_lookup_service import JdmGradeService


def test_local_lookup_includes_verified_factory_grades_when_available():
    service = JdmGradeService(
        supabase_url="http://unused",
        service_role_key="unused",
        sheet_webhook="http://unused",
    )

    async def fake_request(method, table, *, params=None, payload=None):
        if table == "jacc_chassis_codes":
            return [
                {
                    "id": "code-1",
                    "model_id": "model-1",
                    "chassis_prefix_normalized": "GRS210",
                    "body_type": "Sedan",
                    "confidence": "manual",
                    "verified": True,
                }
            ]
        if table == "jacc_vehicle_models":
            return [
                {
                    "id": "model-1",
                    "make_id": "make-1",
                    "canonical_name": "CROWN",
                    "body_type": "Sedan",
                    "vehicle_category": "Sedan",
                }
            ]
        if table == "jacc_vehicle_makes":
            return [{"id": "make-1", "display_name": "Toyota"}]
        if table == "jacc_factory_grades":
            return [
                {
                    "id": "grade-1",
                    "model_id": "model-1",
                    "chassis_code_id": "code-1",
                    "grade_code": "RS",
                    "grade_name": "Royal Saloon",
                    "trim_level": "Royal Saloon",
                    "equipment": {"sunroof": True},
                    "confidence": "verified",
                    "verified": True,
                    "source_id": "source-1",
                }
            ]
        raise AssertionError(f"unexpected table: {table}")

    service._request = fake_request
    result = asyncio.run(service._lookup_local("GRS210"))

    assert result["status"] == "ok"
    assert result["matches"][0]["model"] == "CROWN"
    assert result["matches"][0]["factory_grades"][0]["grade_code"] == "RS"
    assert result["matches"][0]["factory_grades"][0]["verified"] is True
