from app.db.connection import Database


class FakeCursor:
    def __init__(self):
        self.statement = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement, params):
        self.statement, self.params = statement, params

    def fetchone(self):
        return {"probe": "ok", "database_name": "gaokao_agent"}


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakePool:
    def __init__(self, connection):
        self.value = connection

    def connection(self):
        return self.value


def test_parameterized_connection_probe_returns_connection():
    connection = FakeConnection()
    database = Database(None)
    database._pool = FakePool(connection)

    assert database.check_connection()["probe"] == "ok"
    assert connection.cursor_instance.params == ("ok",)
    assert "%s" in connection.cursor_instance.statement
    assert connection.closed


def test_transaction_rolls_back_and_returns_connection_on_failure():
    connection = FakeConnection()
    database = Database(None)
    database._pool = FakePool(connection)

    try:
        with database.transaction():
            raise RuntimeError("failure")
    except RuntimeError:
        pass

    assert connection.rolled_back
    assert not connection.committed
    assert connection.closed

