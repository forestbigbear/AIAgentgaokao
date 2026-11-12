"""Apply and inspect the project's MySQL schema using local .env credentials."""

import argparse
from pathlib import Path

import pymysql
import sqlparse

from app.core.config import PROJECT_ROOT, get_settings


EXPECTED_TABLES = frozenset(
    {
        "students",
        "student_profiles",
        "universities",
        "majors",
        "admission_plans",
        "admission_records",
        "workflow_runs",
        "recommendation_plans",
        "recommendation_items",
        "workflow_events",
        "knowledge_documents",
        "knowledge_chunks",
        "operation_logs",
    }
)
SQL_DIR = PROJECT_ROOT / "sql"


def connect_server() -> pymysql.connections.Connection:
    settings = get_settings()
    if settings.db_name != "gaokao_agent":
        raise ValueError("DB_NAME must be gaokao_agent for the checked-in SQL scripts")
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def apply_file(connection: pymysql.connections.Connection, path: Path) -> None:
    statements = sqlparse.split(path.read_text(encoding="utf-8"))
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                if sqlparse.format(statement, strip_comments=True).strip(" ;\n\r\t"):
                    cursor.execute(statement)
    except Exception:
        connection.rollback()
        raise


def database_status(connection: pymysql.connections.Connection) -> tuple[bool, set[str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            (get_settings().db_name,),
        )
        exists = cursor.fetchone() is not None
        if not exists:
            return False, set()
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = %s",
            (get_settings().db_name, "BASE TABLE"),
        )
        return True, {row["TABLE_NAME"] for row in cursor.fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser(description="MySQL schema setup and checks")
    parser.add_argument("action", choices=("check", "init", "seed"))
    action = parser.parse_args().action

    try:
        with connect_server() as connection:
            if action == "init":
                apply_file(connection, SQL_DIR / "schema.sql")
            elif action == "seed":
                exists, tables = database_status(connection)
                if not exists or not EXPECTED_TABLES.issubset(tables):
                    print("Database schema is incomplete; run init first.")
                    return 1
                apply_file(connection, SQL_DIR / "seed_simulated_data.sql")

            exists, tables = database_status(connection)
            missing = EXPECTED_TABLES - tables
            print(
                f"MySQL connected; database exists: {exists}; "
                f"expected tables: {len(EXPECTED_TABLES) - len(missing)}/{len(EXPECTED_TABLES)}"
            )
            if missing:
                print(f"Missing tables: {', '.join(sorted(missing))}")
            return 0 if exists and not missing else 1
    except pymysql.OperationalError as exc:
        code = exc.args[0] if exc.args else None
        if code == 2003:
            print("MySQL is not listening at DB_HOST:DB_PORT; check the server service.")
        elif code == 1045:
            print("MySQL rejected DB_USER/DB_PASSWORD; check the local .env file.")
        else:
            print(f"MySQL operation failed (error code {code}).")
        return 1
    except (pymysql.MySQLError, OSError) as exc:
        print(f"MySQL connection or SQL execution failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

