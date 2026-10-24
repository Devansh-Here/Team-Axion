from app.contracts import PolicyDecision


def authorize(role: str, dataset_id: str, question: str) -> PolicyDecision:
    # STUB: Kartik real policy likhega
    return PolicyDecision(
        action="ALLOW",
        allowed_tables={"sales", "products", "customers"},
        allowed_columns={
            "sales.order_id", "sales.order_date", "sales.product_id",
            "sales.region", "sales.net_amt", "sales.status",
            "products.product_id", "products.product_name", "products.category",
        },
        reason_code="STUB",
    )