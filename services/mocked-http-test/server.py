import http.server
import json
import logging
import os
from urllib.parse import urlparse

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8008"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class MockHandler(http.server.BaseHTTPRequestHandler):
    def handle_request(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length).decode("utf-8", errors="replace")
            if content_length > 0
            else ""
        )

        request_dump = {
            "method": self.command,
            "path": parsed.path,
            "query": parsed.query,
            "headers": dict(self.headers),
            "body": body,
        }

        logging.info("%s %s from %s", self.command, self.path, self.client_address[0])

        response = json.dumps(request_dump, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self.handle_request
        raise AttributeError(name)

    def log_message(self, format, *args):
        pass  # suppress default access log; we use logging.info in handle_request


def make_server(host=HOST, port=PORT):
    return http.server.ThreadingHTTPServer((host, port), MockHandler)


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    server = make_server()
    logging.info("mocked-http-test listening on %s:%s", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
        server.shutdown()
