# mocked-http-test

A mock HTTP server for development and testing. Accepts any HTTP request on
any path and method, returns HTTP 200 OK with a JSON dump of the request.

## Purpose

Replace real external HTTP APIs (e.g. Express Taxi API) during local testing.

## Configuration (env)

| Variable  | Default     | Description    |
|-----------|-------------|----------------|
| HOST      | 127.0.0.1   | Listen address |
| PORT      | 8008        | Listen port    |
| LOG_LEVEL | INFO        | Logging level  |

## Response format

Every request returns HTTP 200 with JSON:

```json
{
  "method": "GET",
  "path": "/YTaxi/ru/ManagePBX/IncomingCall",
  "query": "provider=test&from=0671234567&line=1",
  "headers": { "Host": "127.0.0.1:8008" },
  "body": ""
}
```

## Installation (systemd)

```bash
sudo cp services/MockedHttpTest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mocked-http-test
sudo systemctl start mocked-http-test
```

## Running manually

```bash
services/mocked-http-test/.python-venv/bin/python services/mocked-http-test/server.py
```

## Testing

```bash
services/mocked-http-test/.python-venv/bin/python -m pytest services/mocked-http-test/tests/ -v

# Manual smoke test
curl -s http://127.0.0.1:8008/test?foo=bar | python3 -m json.tool
curl -s -X POST http://127.0.0.1:8008/api -d '{"key":"val"}' | python3 -m json.tool
```

## Logs

```bash
journalctl -u pearlpbx-mocked-http -f
```
