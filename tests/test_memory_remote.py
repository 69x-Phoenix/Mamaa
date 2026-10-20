import base64
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent import remote_db
from agent.memory import Memory
from agent.remote_db import RemoteError, decode_value, encode_value, pipeline_url
from config import Settings

TOKEN = "super-secret-token-123"


class FakeTurso:
    """A local stand-in for Turso's /v2/pipeline endpoint, backed by an in-memory SQLite database."""

    def __init__(self, token: str = TOKEN) -> None:
        self.token = token
        self.fail = False
        self.requests: list[dict] = []
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return None

            def _reply(self, status: int, payload: dict | None = None) -> None:
                body = json.dumps(payload or {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or b"{}")
                if self.path != "/v2/pipeline":
                    return self._reply(404)
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    return self._reply(401)
                if fake.fail:
                    return self._reply(500)
                fake.requests.append(data)
                results = []
                for req in data["requests"]:
                    if req["type"] == "close":
                        results.append({"type": "ok", "response": {"type": "close"}})
                        continue
                    stmt = req["stmt"]
                    assert "args" not in stmt or stmt["args"], "args must be omitted when empty"
                    args = [fake.decode(a) for a in stmt.get("args", [])]
                    try:
                        with fake.lock:
                            cur = fake.db.execute(stmt["sql"], args)
                            rows = cur.fetchall()
                            fake.db.commit()
                            cols = [{"name": d[0]} for d in (cur.description or [])]
                            last = cur.lastrowid
                    except sqlite3.Error as exc:
                        results.append({"type": "error", "error": {"message": str(exc), "code": "SQLITE_ERROR"}})
                        continue
                    results.append({"type": "ok", "response": {"type": "execute", "result": {
                        "cols": cols, "rows": [[fake.encode(v) for v in row] for row in rows],
                        "affected_row_count": max(cur.rowcount, 0), "last_insert_rowid": str(last) if last else None}}})
                self._reply(200, {"baton": None, "base_url": None, "results": results})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def decode(arg: dict):
        kind = arg["type"]
        if kind == "null":
            return None
        if kind == "integer":
            return int(arg["value"])
        if kind == "float":
            return float(arg["value"])
        if kind == "blob":
            return base64.b64decode(arg["base64"])
        return arg["value"]

    @staticmethod
    def encode(value) -> dict:
        if value is None:
            return {"type": "null"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        if isinstance(value, bytes):
            return {"type": "blob", "base64": base64.b64encode(value).decode()}
        return {"type": "text", "value": value}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake():
    server = FakeTurso()
    yield server
    server.close()


CHAT = [{"role": "user", "content": "নদী ভাঙন নিয়ে বলো", "files": []}, {"role": "assistant", "content": "ঠিক আছে", "files": []}]


def test_everything_works_through_the_hosted_database(fake, tmp_path):
    local = tmp_path / "local.db"
    mem = Memory(local, remote=(fake.url, TOKEN))
    assert mem.backend == "turso" and mem.backend_label == "Permanent (Turso)" and mem.warning == ""
    task = mem.start_task("hello")
    mem.log_tool(task, "calculator", True)
    mem.finish_task(task, "done", "done")
    assert mem.stats() == {"tasks": 1, "tool_calls": 1}
    assert mem.recent_tasks()[0]["request"] == "hello"
    conv = mem.save_conversation(None, "নদী ভাঙন", CHAT)
    assert mem.save_conversation(conv, "নদী ভাঙন (২)", CHAT) == conv  # update, not a second row
    assert mem.load_conversation(conv) == CHAT
    assert [c["title"] for c in mem.list_conversations()] == ["নদী ভাঙন (২)"]
    assert mem.list_conversations(query="ভাঙন") and mem.list_conversations(query="zzz") == []
    mem.delete_conversation(conv)
    assert mem.load_conversation(conv) is None
    mem.clear()
    assert mem.stats() == {"tasks": 0, "tool_calls": 0}
    assert not local.exists()  # nothing was written to the local disk


def test_search_treats_wildcards_literally(tmp_path):
    mem = Memory(tmp_path / "m.db")
    mem.save_conversation(None, "100% sure", CHAT)
    mem.save_conversation(None, "other", CHAT)
    assert [c["title"] for c in mem.list_conversations(query="100%")] == ["100% sure"]
    assert len(mem.list_conversations(query="%")) == 1  # '%' only matches a real percent sign


def test_wrong_token_falls_back_to_local_and_never_leaks_the_token(fake, tmp_path):
    mem = Memory(tmp_path / "local.db", remote=(fake.url, "wrong-token-abc"))
    assert mem.backend == "fallback" and "Temporary" in mem.backend_label
    assert "credentials" in mem.warning and "wrong-token-abc" not in mem.warning and TOKEN not in mem.warning
    assert mem.start_task("still works") == 1 and (tmp_path / "local.db").exists()


def test_server_down_falls_back(tmp_path):
    dead = FakeTurso()
    url = dead.url
    dead.close()
    mem = Memory(tmp_path / "local.db", remote=(url, TOKEN))
    assert mem.backend == "fallback" and "could not reach" in mem.warning
    assert mem.stats() == {"tasks": 0, "tool_calls": 0}


def test_failure_in_the_middle_of_a_session_switches_to_local(fake, tmp_path):
    mem = Memory(tmp_path / "local.db", remote=(fake.url, TOKEN))
    assert mem.start_task("one") == 1
    fake.fail = True
    assert mem.start_task("two") == 1  # answered by the new local file
    assert mem.backend == "fallback" and mem.stats()["tasks"] == 1


def test_reads_are_cached_briefly_and_writes_refresh_them(fake, tmp_path):
    mem = Memory(tmp_path / "local.db", remote=(fake.url, TOKEN))
    mem.stats()
    before = len(fake.requests)
    mem.stats()
    mem.stats()
    assert len(fake.requests) == before  # served from the cache
    mem.start_task("x")
    assert mem.stats()["tasks"] == 1


def test_url_rules_and_value_encoding():
    assert pipeline_url("libsql://db-org.turso.io") == "https://db-org.turso.io/v2/pipeline"
    assert pipeline_url("https://db-org.turso.io/") == "https://db-org.turso.io/v2/pipeline"
    assert pipeline_url("http://127.0.0.1:9") == "http://127.0.0.1:9/v2/pipeline"
    for bad in ["http://example.com", "ftp://x", "", "db-org.turso.io"]:
        with pytest.raises(RemoteError):
            pipeline_url(bad)
    for value in [None, 7, 2**62, -3, 1.5, "বাংলা", b"\x00\x01"]:
        assert decode_value(encode_value(value)) == value
    assert encode_value(2**62) == {"type": "integer", "value": str(2**62)}
    assert encode_value(True) == {"type": "integer", "value": "1"}


def test_settings_pick_the_hosted_database_only_when_both_values_exist(tmp_path):
    base = dict(gemini_api_key="x", model="m", app_password="", max_steps=4, log_level="INFO",
                workspace_dir=tmp_path, db_path=tmp_path / "d.db")
    assert Settings(**base).remote_db() is None
    assert Settings(**base, turso_url="libsql://a.turso.io").remote_db() is None
    assert Settings(**base, turso_url="libsql://a.turso.io", turso_token="t").remote_db() == ("libsql://a.turso.io", "t")


def test_memory_module_never_logs_the_token():
    source = open(remote_db.__file__, encoding="utf-8").read()
    assert source.count("self._token") == 2  # stored once, used once in the Authorization header
