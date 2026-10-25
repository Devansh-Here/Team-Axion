from app.policy import ROLE_LIMITS, authorize, permitted_schema


def test_three_roles_have_distinct_limits_and_server_side_schemas():
    assert set(ROLE_LIMITS) == {"owner", "analyst", "viewer"}
    assert ROLE_LIMITS["owner"]["row_limit"] > ROLE_LIMITS["analyst"]["row_limit"] > ROLE_LIMITS["viewer"]["row_limit"]
    assert ROLE_LIMITS["owner"]["column_limit"] > ROLE_LIMITS["analyst"]["column_limit"] > ROLE_LIMITS["viewer"]["column_limit"]
    assert "email" in permitted_schema("analyst", "crm_demo")["contacts"]
    assert "email" not in permitted_schema("viewer", "crm_demo")["contacts"]


def test_owner_does_not_bypass_protected_data_approval():
    decision = authorize("owner", "demo", "show employee salary")
    assert decision.action == "ASK"
    assert decision.allowed_columns == set()
