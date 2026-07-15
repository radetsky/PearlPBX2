.PHONY: test test-coverage test-quick test-app test-build test-down api-docs

# Generate the API reference for third-party developers:
#   docs/openapi.yaml  — machine-readable OpenAPI 3.0 schema (Postman/Insomnia, SDK codegen)
#   docs/api.html      — self-contained, offline browsable reference (no token, no network)
# The HTML step needs Node.js/npx; the first run downloads @redocly/cli.
api-docs:
	.python-venv/bin/python manage.py spectacular --file docs/openapi.yaml
	npx --yes @redocly/cli build-docs docs/openapi.yaml -o docs/api.html

test-build:
	docker compose -f docker-compose.test.yml build

test: test-build
	docker compose -f docker-compose.test.yml run --rm test

test-coverage: test-build
	docker compose -f docker-compose.test.yml run --rm test \
		--cov=core --cov=apps --cov-report=html --cov-report=term-missing

test-quick: test-build
	docker compose -f docker-compose.test.yml run --rm test --no-cov -x

test-app: test-build
	docker compose -f docker-compose.test.yml run --rm test $(APP)

test-down:
	docker compose -f docker-compose.test.yml down -v
