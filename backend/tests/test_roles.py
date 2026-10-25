from app.policy import authorize, permitted_schema, row_filters


def test_three_roles_differ():
    v = permitted_schema("viewer", "demo")
    a = permitted_schema("analyst", "demo")
    m = permitted_schema("manager", "demo")
    assert "employees" not in v
    assert "customer_name" not in v["customers"]
    assert "customer_name" not in a["customers"]
    assert "salary" not in m.get("employees", [])
    assert "salary" not in a.get("employees", [])


def test_salary_actions():
    q = "average employee salary by department"
    assert authorize("viewer", "demo", q).action == "DENY"
    assert authorize("analyst", "demo", q).action == "ASK"
    assert authorize("manager", "demo", q).action == "ASK"


def test_row_filter_only_viewer():
    assert row_filters("viewer", "demo")
    assert not row_filters("analyst", "demo")
    assert not row_filters("manager", "demo")