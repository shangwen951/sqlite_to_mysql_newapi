#!/usr/bin/env python3
"""Export a New API SQLite database to a MySQL-importable SQL file."""

from __future__ import annotations

import argparse
import math
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote


TEXT_LIKE = {"TEXT", "CLOB"}
BLOB_LIKE = {"BLOB"}


def mysql_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def sqlite_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def mysql_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\0", "\\0")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\x1a", "\\Z")
        .replace("'", "\\'")
    )
    return "'" + escaped + "'"


def mysql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else "NULL"
    return mysql_string(str(value))


def normalize_sqlite_type(sqlite_type: str) -> str:
    return (sqlite_type or "").strip().upper()


def mysql_column_type(sqlite_type: str, is_primary_key: bool) -> str:
    t = normalize_sqlite_type(sqlite_type)
    if not t:
        return "LONGTEXT"

    varchar_match = re.fullmatch(r"(?:VAR)?CHAR\s*\(\s*(\d+)\s*\)", t)
    if varchar_match:
        return f"VARCHAR({varchar_match.group(1)})"

    if re.fullmatch(r"N?VARCHAR\s*\(\s*(\d+)\s*\)", t):
        return t

    if "INT" in t:
        return "BIGINT"
    if any(part in t for part in ("DOUBLE", "FLOAT", "REAL")):
        return "DOUBLE"
    if "DECIMAL" in t:
        return t
    if "NUMERIC" in t or "BOOLEAN" in t:
        return "DECIMAL(20,6)"
    if "DATE" in t or "TIME" in t:
        return "DATETIME"
    if "JSON" in t:
        return "LONGTEXT"
    if any(part in t for part in BLOB_LIKE):
        return "LONGBLOB"
    if any(part in t for part in TEXT_LIKE) or "CHAR" in t:
        return "VARCHAR(191)" if is_primary_key else "LONGTEXT"
    return "LONGTEXT"


def mysql_default(raw_default: str | None, column_type: str) -> str:
    if raw_default is None:
        return ""

    upper_type = column_type.upper()
    if "TEXT" in upper_type or "BLOB" in upper_type:
        return ""

    value = raw_default.strip()
    upper_value = value.upper()
    if upper_value == "NULL":
        return " DEFAULT NULL"
    if upper_value == "FALSE":
        return " DEFAULT 0"
    if upper_value == "TRUE":
        return " DEFAULT 1"
    if upper_value in {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"}:
        return f" DEFAULT {upper_value}"

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return " DEFAULT " + mysql_string(value[1:-1])

    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return " DEFAULT " + value

    return ""


def readonly_uri(path: Path) -> str:
    posix_path = path.resolve().as_posix()
    return "file:" + quote(posix_path, safe="/:") + "?mode=ro"


def fetch_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows]


def fetch_columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({sqlite_ident(table)})").fetchall()


def create_table_sql(conn: sqlite3.Connection, table: str) -> str:
    columns = fetch_columns(conn, table)
    primary_key_columns = [col for col in sorted(columns, key=lambda col: col["pk"]) if col["pk"]]
    single_integer_pk = (
        len(primary_key_columns) == 1
        and "INT" in normalize_sqlite_type(primary_key_columns[0]["type"])
    )

    lines: list[str] = []
    for col in columns:
        is_pk = bool(col["pk"])
        col_type = mysql_column_type(col["type"], is_pk)
        line = f"  {mysql_ident(col['name'])} {col_type}"
        if col["notnull"] or is_pk:
            line += " NOT NULL"
        else:
            line += " NULL"
        if single_integer_pk and is_pk:
            line += " AUTO_INCREMENT"
        line += mysql_default(col["dflt_value"], col_type)
        lines.append(line)

    if primary_key_columns:
        pk = ", ".join(mysql_ident(col["name"]) for col in primary_key_columns)
        lines.append(f"  PRIMARY KEY ({pk})")

    body = ",\n".join(lines)
    return (
        f"CREATE TABLE {mysql_ident(table)} (\n"
        f"{body}\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
    )


def write_inserts(
    conn: sqlite3.Connection,
    table: str,
    columns: list[sqlite3.Row],
    out,
    batch_size: int,
) -> int:
    col_names = [col["name"] for col in columns]
    select_cols = ", ".join(sqlite_ident(name) for name in col_names)
    insert_cols = ", ".join(mysql_ident(name) for name in col_names)
    cursor = conn.execute(f"SELECT {select_cols} FROM {sqlite_ident(table)}")
    total = 0

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        out.write(f"INSERT INTO {mysql_ident(table)} ({insert_cols}) VALUES\n")
        values = []
        for row in rows:
            values.append("  (" + ", ".join(mysql_value(value) for value in row) + ")")
        out.write(",\n".join(values))
        out.write(";\n")
        total += len(rows)

    return total


def export_dump(sqlite_db: Path, output_sql: Path, batch_size: int) -> None:
    conn = sqlite3.connect(readonly_uri(sqlite_db), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = fetch_tables(conn)
        with output_sql.open("w", encoding="utf-8", newline="\n") as out:
            out.write("-- Generated by sqlite_to_mysql_newapi.py\n")
            out.write("SET NAMES utf8mb4;\n")
            out.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

            for table in tables:
                columns = fetch_columns(conn, table)
                out.write(f"-- Table: {table}\n")
                out.write(f"DROP TABLE IF EXISTS {mysql_ident(table)};\n")
                out.write(create_table_sql(conn, table))
                out.write("\n\n")
                row_count = write_inserts(conn, table, columns, out, batch_size)
                out.write(f"-- Rows exported from {table}: {row_count}\n\n")

            out.write("SET FOREIGN_KEY_CHECKS=1;\n")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export New API SQLite tables and rows to a MySQL-importable SQL file."
    )
    parser.add_argument("sqlite_db", nargs="?", default="one-api.db", help="SQLite database file")
    parser.add_argument(
        "output_sql",
        nargs="?",
        default="one-api.sql",
        help="Output MySQL SQL file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per INSERT statement",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sqlite_db = Path(args.sqlite_db)
    output_sql = Path(args.output_sql)

    if not sqlite_db.exists():
        raise SystemExit(f"SQLite数据库未找到: {sqlite_db}")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size 必须大于 0")

    export_dump(sqlite_db, output_sql, args.batch_size)
    print(f"已导出 {sqlite_db} to {output_sql}")


if __name__ == "__main__":
    main()
