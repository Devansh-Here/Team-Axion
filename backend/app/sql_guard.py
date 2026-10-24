"""SQL guard: model ka SQL execute hone se pehle AST se check hota hai.
Rule: sirf ek SELECT, sirf allowed tables/columns, sirf allowed functions.
Koi bhi doubt ya error aaye to REJECT (fail closed).
Reject reasons mein column/table ke naam nahi daalte (protected fields leak na ho).
"""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

MAX_SQL_CHARS = 5000


@dataclass
class Allow:
    ast: object = None


@dataclass
class Reject:
    reason: str


# Sirf ye functions allowed hain. Baaki sab reject (load_extension, readfile, randomblob...)
ALLOWED_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "ABS", "LOWER", "UPPER",
    "TRIM", "LENGTH", "SUBSTR", "SUBSTRING", "COALESCE", "IFNULL", "NULLIF",
    "CAST", "CASE", "IF", "DATE", "STRFTIME", "TIMETOSTR", "TIME_TO_STR",
    "JULIANDAY", "ROW_NUMBER",
    "TS_OR_DS_TO_TIMESTAMP", "TS_OR_DS_TO_DATE", "TS_OR_DS_TO_TIME",
}
# Ye node types kahin bhi mile (nested bhi) to reject
_FORBIDDEN_NAMES = [
    "Insert", "Update", "Delete", "Create", "Drop", "Alter", "Command",
    "Pragma", "Attach", "Detach", "Merge", "Transaction", "Commit",
    "Rollback", "Set", "Use", "TruncateTable",
]
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))

_ROOT_NAMES = ["Select", "Union", "Intersect", "Except", "SetOperation"]
ALLOWED_ROOTS = tuple(getattr(exp, n) for n in _ROOT_NAMES if hasattr(exp, n))


def validate_candidate(sql: str, allowed_tables: set[str], allowed_columns: set[str]):
    try:
        return _validate(sql, allowed_tables, allowed_columns)
    except Exception:
        return Reject("GUARD_INTERNAL_ERROR")  # fail closed


def _validate(sql, allowed_tables, allowed_columns):
    # 1. basic input checks
    if not isinstance(sql, str) or not sql.strip():
        return Reject("EMPTY_SQL")
    if len(sql) > MAX_SQL_CHARS:
        return Reject("SQL_TOO_LONG")

    tables_ok = {t.lower() for t in allowed_tables}
    cols_ok = {c.lower() for c in allowed_columns}

    # 2. parse (SQLite dialect)
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except Exception:
        return Reject("PARSE_ERROR")

    # 3. exactly one statement
    if len(statements) != 1:
        return Reject("NOT_SINGLE_STATEMENT")
    tree = statements[0]

    # 4. root must be SELECT (ya UNION type)
    if not isinstance(tree, ALLOWED_ROOTS):
        return Reject("NOT_SELECT")

    # 5. koi forbidden node nested bhi nahi
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return Reject("FORBIDDEN_STATEMENT")

    # 6. functions allowlist
    for func in tree.find_all(exp.Func):
        name = func.name if isinstance(func, exp.Anonymous) else func.sql_name()
        if name.upper() not in ALLOWED_FUNCTIONS:
            return Reject(f"FUNCTION_NOT_ALLOWED:{name}")

    # 7. bare * reject (COUNT(*) allowed)
    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            return Reject("SELECT_STAR_NOT_ALLOWED")

    # 8. CTE rules: self-reference / recursion nahi (shadowing hole band)
    cte_names = set()
    for cte in tree.find_all(exp.CTE):
        cname = cte.alias.lower()
        cte_names.add(cname)
        if cname.startswith("sqlite_"):
            return Reject("CTE_NAME_NOT_ALLOWED")
        for t in cte.this.find_all(exp.Table):
            if t.name.lower() == cname:
                return Reject("CTE_SELF_REFERENCE")

    # 9. schema map banao: sirf allowed tables + allowed columns
    schema: dict[str, dict[str, str]] = {}
    for item in cols_ok:
        if "." not in item:
            continue
        t, c = item.split(".", 1)
        if t in tables_ok:
            schema.setdefault(t, {})[c] = "TEXT"

    # 10. har table check
    for table in tree.find_all(exp.Table):
        if table.args.get("db") or table.args.get("catalog"):
            return Reject("SCHEMA_QUALIFIED_TABLE")
        if not isinstance(table.this, exp.Identifier):
            return Reject("TABLE_FUNCTION_NOT_ALLOWED")
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in schema:
            return Reject("TABLE_NOT_ALLOWED")

    # 11. columns resolve karo (CTE/subquery/alias ke andar bhi)
    try:
        qualified = qualify(
            tree.copy(), schema=schema, dialect="sqlite",
            validate_qualify_columns=True, expand_stars=True,
        )
    except Exception:
        return Reject("COLUMN_NOT_ALLOWED_OR_UNRESOLVED")

    # 12. double check: base table ke columns allowed list mein hone chahiye
    alias_map = {}
    for table in qualified.find_all(exp.Table):
        tname = table.name.lower()
        if tname in cte_names:
            continue
        alias_map[(table.alias or table.name).lower()] = tname
    for col in qualified.find_all(exp.Column):
        q = col.table.lower() if col.table else ""
        if q in alias_map:
            if f"{alias_map[q]}.{col.name.lower()}" not in cols_ok:
                return Reject("COLUMN_NOT_ALLOWED")

    # qualify() can leave columns in HAVING/GROUP BY/window expressions
    # unqualified. Check the original AST as well so a protected column
    # cannot slip through those clauses (for example HAVING MAX(salary)).
    allowed_unqualified = {
        item.rsplit(".", 1)[1]
        for item in cols_ok
        if "." in item
    }
    select_aliases = {
        alias.alias_or_name.lower()
        for alias in tree.find_all(exp.Alias)
        if alias.alias_or_name
    }

    def is_alias_reference(column):
        parent = column.parent
        while parent is not None:
            if isinstance(parent, (exp.Having, exp.Group, exp.Order, exp.Window)):
                return True
            if isinstance(parent, exp.Select):
                return False
            parent = parent.parent
        return False

    for col in tree.find_all(exp.Column):
        if col.table:
            continue
        name = col.name.lower()
        if name in allowed_unqualified:
            continue
        if name in select_aliases and is_alias_reference(col):
            continue
        return Reject("COLUMN_NOT_ALLOWED")

    return Allow(ast=tree)
