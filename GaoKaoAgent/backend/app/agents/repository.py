import json

from app.db.connection import Database
from app.db.repository import Repository


def _summary(value: dict | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) > 4000:
        encoded = json.dumps({"truncated": True, "preview": encoded[:3500]}, ensure_ascii=False)
    return encoded


class WorkflowRepository:
    def __init__(self, database: Database):
        self.database = database
        self.basic = Repository(database)

    def get_student(self, student_id: int) -> dict | None:
        return self.basic.get_student(student_id)

    def create_run(self, student_id: int, max_adjustments: int) -> int:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workflow_runs (student_id, status, current_node, max_adjustments) "
                "VALUES (%s, 'running', 'student_profile', %s)",
                (student_id, max_adjustments),
            )
            return cursor.lastrowid

    def add_event(self, run_id: int, agent: str, status: str, inputs: dict,
                  outputs: dict | None = None, error: str | None = None) -> None:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE workflow_runs SET current_node = %s WHERE id = %s",
                (agent, run_id),
            )
            cursor.execute(
                "INSERT INTO workflow_events "
                "(workflow_run_id, agent_name, event_type, status, input_summary, output_summary, error_message) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (run_id, agent, "node", status,
                 _summary(inputs), _summary(outputs),
                 error),
            )

    def save_profile(self, student_id: int, profile: dict, issues: list[str]) -> None:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO student_profiles (student_id, profile_json, validation_warnings) "
                "VALUES (%s, %s, %s)",
                (student_id, json.dumps(profile, ensure_ascii=False, default=str),
                 json.dumps(issues, ensure_ascii=False)),
            )

    def retrieve_candidates(self, province: str, exam_year: int, history_years: int,
                            limit: int) -> tuple[list[dict], bool]:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.id AS plan_id, p.university_id, p.major_id, p.province AS plan_province, "
                "p.exam_year AS plan_year, p.batch_name, p.planned_count, "
                "p.subject_requirements AS plan_subjects, p.source_name AS plan_source, "
                "p.source_url AS plan_url, p.updated_at AS plan_updated_at, "
                "u.name AS university_name, u.city, u.applicable_year AS university_year, "
                "u.source_name AS university_source, m.name AS major_name, m.category, "
                "m.subject_requirements AS major_subjects, m.applicable_year AS major_year, "
                "m.source_name AS major_source "
                "FROM admission_plans AS p JOIN universities AS u ON u.id = p.university_id "
                "JOIN majors AS m ON m.id = p.major_id AND m.university_id = p.university_id "
                "WHERE p.province = %s AND p.exam_year = %s ORDER BY p.id LIMIT %s",
                (province, exam_year, limit + 1),
            )
            rows = cursor.fetchall()
            truncated = len(rows) > limit
            rows = rows[:limit]
            if not rows:
                return [], False
            major_ids = sorted({row["major_id"] for row in rows})
            placeholders = ", ".join(["%s"] * len(major_ids))
            cursor.execute(
                "SELECT r.id, r.university_id, r.major_id, r.province, r.exam_year, "
                "r.batch_name, r.min_score, r.min_rank_no, r.source_name, r.source_url, r.updated_at "
                "FROM admission_records AS r WHERE r.province = %s "
                "AND r.exam_year >= %s AND r.exam_year < %s "
                f"AND r.major_id IN ({placeholders}) ORDER BY r.exam_year DESC",
                (province, exam_year - history_years, exam_year, *major_ids),
            )
            records = cursor.fetchall()
        by_key: dict[tuple, list[dict]] = {}
        for record in records:
            key = (record["university_id"], record["major_id"], record["batch_name"])
            by_key.setdefault(key, []).append(record)
        for row in rows:
            row["history"] = by_key.get(
                (row["university_id"], row["major_id"], row["batch_name"]), []
            )
        return rows, truncated

    def save_plan(self, run_id: int, student_id: int, exam_year: int,
                  items: list[dict], summary: str) -> int | None:
        if not items:
            return None
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO recommendation_plans "
                "(student_id, exam_year, status, workflow_run_id, summary) "
                "VALUES (%s, %s, 'generated', %s, %s)",
                (student_id, exam_year, run_id, summary),
            )
            plan_id = cursor.lastrowid
            cursor.executemany(
                "INSERT INTO recommendation_items "
                "(plan_id, university_id, major_id, tier, match_score, reason_text, "
                "evidence_json, risk_level, risk_notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(plan_id, item["university_id"], item["major_id"], item["tier"],
                  item["match_score"], item["reason_text"],
                  json.dumps(item["evidence"], ensure_ascii=False, default=str),
                  item["risk_level"], item["risk_notes"]) for item in items],
            )
            return plan_id

    def finish(self, run_id: int, status: str, adjustment_count: int,
               error: str | None = None) -> None:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE workflow_runs SET status = %s, current_node = NULL, "
                "adjustment_count = %s, error_message = %s, finished_at = NOW() WHERE id = %s",
                (status, adjustment_count, error, run_id),
            )

    def get_run(self, run_id: int) -> dict | None:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM workflow_runs WHERE id = %s", (run_id,))
            run = cursor.fetchone()
            if run is None:
                return None
            cursor.execute(
                "SELECT * FROM workflow_events WHERE workflow_run_id = %s ORDER BY id",
                (run_id,),
            )
            run["events"] = cursor.fetchall()
            for event in run["events"]:
                for field in ("input_summary", "output_summary"):
                    if event[field]:
                        event[field] = json.loads(event[field])
            cursor.execute(
                "SELECT id FROM recommendation_plans WHERE workflow_run_id = %s", (run_id,)
            )
            plan = cursor.fetchone()
        run["plan"] = self.basic.get_plan(plan["id"]) if plan else None
        return run
