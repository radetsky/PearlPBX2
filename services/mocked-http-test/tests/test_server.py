import json
import threading
import time
import unittest
import urllib.request


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 18008  # test port, not 8008


def start_test_server():
    import importlib
    import os
    import sys

    _env_keys = ("HOST", "PORT", "LOG_LEVEL")
    _saved_env = {k: os.environ.get(k) for k in _env_keys}

    os.environ["HOST"] = SERVER_HOST
    os.environ["PORT"] = str(SERVER_PORT)
    os.environ["LOG_LEVEL"] = "WARNING"
    sys.path.insert(0, "services/mocked-http-test")

    import server
    importlib.reload(server)

    srv = server.make_server(SERVER_HOST, SERVER_PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.1)
    return srv, _saved_env


class TestMockedHttpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        import sys
        cls.server, cls._saved_env = start_test_server()
        cls._sys = sys
        cls._os = os
        cls.base = f"http://{SERVER_HOST}:{SERVER_PORT}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for k, v in cls._saved_env.items():
            if v is None:
                cls._os.environ.pop(k, None)
            else:
                cls._os.environ[k] = v
        try:
            cls._sys.path.remove("services/mocked-http-test")
        except ValueError:
            pass

    def _get(self, path):
        req = urllib.request.Request(f"{self.base}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, path, body=b"hello"):
        req = urllib.request.Request(
            f"{self.base}{path}", data=body, method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def test_get_returns_200(self):
        status, _ = self._get("/")
        self.assertEqual(status, 200)

    def test_get_returns_method(self):
        _, body = self._get("/some/path")
        self.assertEqual(body["method"], "GET")

    def test_get_returns_path(self):
        _, body = self._get("/some/path")
        self.assertEqual(body["path"], "/some/path")

    def test_get_returns_query(self):
        _, body = self._get("/x?foo=bar&baz=1")
        self.assertEqual(body["query"], "foo=bar&baz=1")

    def test_post_returns_200(self):
        status, _ = self._post("/api/call", b"data")
        self.assertEqual(status, 200)

    def test_post_returns_body(self):
        _, body = self._post("/api/call", b"payload")
        self.assertEqual(body["body"], "payload")

    def test_post_returns_method(self):
        _, body = self._post("/api/call")
        self.assertEqual(body["method"], "POST")

    def test_any_path_accepted(self):
        for path in ["/", "/a/b/c", "/YTaxi/ru/ManagePBX/IncomingCall"]:
            status, _ = self._get(path)
            self.assertEqual(status, 200, f"Failed for path: {path}")

    def test_response_has_headers_key(self):
        _, body = self._get("/")
        self.assertIn("headers", body)
        self.assertIsInstance(body["headers"], dict)


if __name__ == "__main__":
    unittest.main()
