import json

from app.db.connection import Database


STUDENT_COLUMNS = (
    "province", "exam_year", "score", "rank_no", "subject_combination",
    "interests", "target_cities", "risk_preference",
)


def _student(row: dict | None) -> dict | None:
    if row:
        for field in ("interests", "target_cities"):
            row[field] = json.loads(row[field]) if isinstance(row[field], str) else row[field] or []
    return row


def _item(row: dict) -> dict:
    value = row.pop("evidence_json")
    row["evidence"] = json.loads(value) if isinstance(value, str) else value or {}
    return row


class Repository:
    def __init__(self, database: Database):
        self.database = database

    def get_student(self, student_id: int, connection=None) -> dict | None:
        if connection is None:
            with self.database.connection() as db:
                return self.get_student(student_id, db)
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
            return _student(cursor.fetchone())

    def list_students(self, page: int, page_size: int) -> tuple[list[dict], int]:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM students")
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT * FROM students ORDER BY id DESC LIMIT %s OFFSET %s",
                (page_size, (page - 1) * page_size),
            )
            return [_student(row) for row in cursor.fetchall()], total

    def create_student(self, values: dict) -> dict:
        data = values.copy()
        for field in ("interests", "target_cities"):
            data[field] = json.dumps(data[field], ensure_ascii=False)
        columns = ", ".join(STUDENT_COLUMNS)
        placeholders = ", ".join(["%s"] * len(STUDENT_COLUMNS))
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO students ({columns}) VALUES ({placeholders})",
                    tuple(data[column] for column in STUDENT_COLUMNS),
                )
                student_id = cursor.lastrowid
            return self.get_student(student_id, connection)

    def update_student(self, student_id: int, values: dict) -> dict | None:
        data = values.copy()
        for field in ("interests", "target_cities"):
            if field in data:
                data[field] = json.dumps(data[field], ensure_ascii=False)
        # Column names come exclusively from the validated StudentUpdate model.
        columns = [field for field in STUDENT_COLUMNS if field in data]
        assignments = ", ".join(f"{column} = %s" for column in columns)
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE students SET {assignments} WHERE id = %s",
                    (*[data[column] for column in columns], student_id),
                )
                if cursor.rowcount == 0:
                    return self.get_student(student_id, connection)
            return self.get_student(student_id, connection)

    def list_catalog(self, resource: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
        configs = {
            "universities": ("universities AS u", "u", {
                "province": "u.province", "year": "u.applicable_year",
                "name": "u.name", "city": "u.city",
            }),
            "majors": ("majors AS m JOIN universities AS u ON u.id = m.university_id", "m", {
                "university_id": "m.university_id", "year": "m.applicable_year",
                "name": "m.name", "subject": "m.subject_requirements",
                "province": "u.province",
            }),
            "admission_plans": (
                "admission_plans AS a JOIN universities AS u ON u.id = a.university_id "
                "JOIN majors AS m ON m.id = a.major_id", "a", {
                    "province": "a.province", "year": "a.exam_year",
                    "university_id": "a.university_id", "major_id": "a.major_id",
                    "university_name": "u.name", "major_name": "m.name",
                    "subject": "a.subject_requirements",
                },
            ),
            "admission_records": (
                "admission_records AS a JOIN universities AS u ON u.id = a.university_id "
                "JOIN majors AS m ON m.id = a.major_id", "a", {
                    "province": "a.province", "year": "a.exam_year",
                    "university_id": "a.university_id", "major_id": "a.major_id",
                    "university_name": "u.name", "major_name": "m.name",
                },
            ),
        }
        source, alias, allowed = configs[resource]
        where, params = [], []
        for field, value in filters.items():
            if value is None or value == "":
                continue
            column = allowed[field]
            if field in {"name", "university_name", "major_name", "subject"}:
                where.append(f"{column} LIKE %s")
                params.append(f"%{value}%")
            else:
                where.append(f"{column} = %s")
                params.append(value)
        where_sql = " WHERE " + " AND ".join(where) if where else ""
        if resource == "majors":
            select = "m.*, u.name AS university_name, u.province AS university_province"
        elif resource in {"admission_plans", "admission_records"}:
            select = "a.*, u.name AS university_name, m.name AS major_name"
        else:
            select = "u.*"
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {source}{where_sql}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT {select} FROM {source}{where_sql} ORDER BY {alias}.id DESC "
                "LIMIT %s OFFSET %s", (*params, page_size, (page - 1) * page_size),
            )
            return cursor.fetchall(), total

    def candidate_exists(self, connection, university_id: int, major_id: int, province: str, year: int) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM admission_plans WHERE university_id = %s AND major_id = %s "
                "AND province = %s AND exam_year = %s LIMIT 1",
                (university_id, major_id, province, year),
            )
            return cursor.fetchone() is not None

    def create_plan(self, student: dict, values: dict) -> dict:
        with self.database.transaction() as connection:
            # Lock the student so a concurrent update cannot change its province/year during validation.
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM students WHERE id = %s FOR UPDATE", (student["id"],))
                current_student = cursor.fetchone()
                if current_student is None:
                    return None
                province, year = current_student["province"], current_student["exam_year"]
                for item in values["items"]:
                    if not self.candidate_exists(connection, item["university_id"], item["major_id"], province, year):
                        return {"invalid_candidate": [item["university_id"], item["major_id"]]}
                cursor.execute(
                    "INSERT INTO recommendation_plans (student_id, exam_year, status, summary) "
                    "VALUES (%s, %s, %s, %s)",
                    (student["id"], year, "draft", values["summary"]),
                )
                plan_id = cursor.lastrowid
                for item in values["items"]:
                    cursor.execute(
                        "INSERT INTO recommendation_items (plan_id, university_id, major_id, tier, "
                        "match_score, reason_text, evidence_json, risk_level, risk_notes) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            plan_id, item["university_id"], item["major_id"], item["tier"],
                            item["match_score"], item["reason_text"],
                            json.dumps(item["evidence"], ensure_ascii=False),
                            item["risk_level"], item["risk_notes"],
                        ),
                    )
            return self.get_plan(plan_id, connection)

    def get_plan(self, plan_id: int, connection=None) -> dict | None:
        if connection is None:
            with self.database.connection() as db:
                return self.get_plan(plan_id, db)
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM recommendation_plans WHERE id = %s", (plan_id,))
            plan = cursor.fetchone()
            if plan is None:
                return None
            cursor.execute(
                "SELECT i.*, u.name AS university_name, m.name AS major_name "
                "FROM recommendation_items AS i "
                "JOIN universities AS u ON u.id = i.university_id "
                "JOIN majors AS m ON m.id = i.major_id "
                "WHERE i.plan_id = %s ORDER BY i.id", (plan_id,),
            )
            plan["items"] = [_item(row) for row in cursor.fetchall()]
            return plan

    def list_plans(self, student_id: int, page: int, page_size: int) -> tuple[list[dict], int]:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM recommendation_plans WHERE student_id = %s", (student_id,))
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT p.*, COUNT(i.id) AS item_count FROM recommendation_plans AS p "
                "LEFT JOIN recommendation_items AS i ON i.plan_id = p.id "
                "WHERE p.student_id = %s GROUP BY p.id ORDER BY p.id DESC LIMIT %s OFFSET %s",
                (student_id, page_size, (page - 1) * page_size),
            )
            return cursor.fetchall(), total
