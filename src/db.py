"""Small MySQL helper: engine creation and a runner for multi-statement .sql files."""
import re

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from config import MYSQL, SQL_DIR


def get_engine(with_database: bool = True):
    url = URL.create(
        "mysql+pymysql",
        username=MYSQL["user"], password=MYSQL["password"],
        host=MYSQL["host"], port=MYSQL["port"],
        database=MYSQL["database"] if with_database else None,
    )
    return create_engine(url, future=True)


def split_sql(script: str) -> list[str]:
    """Strip '-- comments' and split a script on ';' (semicolons inside quotes are kept)."""
    no_comments = "\n".join(re.sub(r"(^|\s)--\s.*$", "", line) for line in script.splitlines())
    statements, buf, in_quote = [], [], False
    for ch in no_comments:
        if ch == "'":
            in_quote = not in_quote
        if ch == ";" and not in_quote:
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    statements.append("".join(buf))
    return [s.strip() for s in statements if s.strip()]


def run_sql_file(conn, filename: str, params: dict | None = None) -> list[pd.DataFrame]:
    """Execute every statement of sql/<filename> on one connection.

    `params` become MySQL session variables (@name) so the .sql files stay plain SQL.
    Returns the result sets of statements that produce rows (SELECTs)."""
    for name, value in (params or {}).items():
        conn.execute(text(f"SET @{name} = :v"), {"v": value})
    results = []
    for stmt in split_sql((SQL_DIR / filename).read_text(encoding="utf-8")):
        res = conn.execute(text(stmt))
        if res.returns_rows:
            results.append(pd.DataFrame(res.fetchall(), columns=list(res.keys())))
    return results


def read_table(query: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(query), conn)
