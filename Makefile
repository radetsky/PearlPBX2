.PHONY: help test test-coverage test-quick test-app test-build test-down api-docs \
	integration-build integration-test integration-down \
	docker-up docker-dev docker-stop docker-clean

.DEFAULT_GOAL := help

help:
	@echo "PearlPBX2 — available targets:"
	@echo ""
	@echo "  docker-up      Start the full stack in the background, production-like (no dev override)"
	@echo "  docker-dev     Start the full stack in the foreground with hot reload (dev override)"
	@echo "  docker-stop    Stop running containers (keeps volumes/data)"
	@echo "  docker-clean   Stop and remove containers, volumes, local images, and network"
	@echo ""
	@echo "  test           Run the test suite (mocked Asterisk)"
	@echo "  test-coverage  Run tests with coverage report"
	@echo "  test-quick     Run tests, stop on first failure, skip coverage"
	@echo "  test-app       Run tests for one app: make test-app APP=core"
	@echo "  test-down      Tear down the test stack"
	@echo ""
	@echo "  integration-test  Run integration tests against a real Asterisk container"
	@echo "  integration-down  Tear down the integration stack"
	@echo ""
	@echo "  api-docs       Generate OpenAPI schema and HTML API reference"

docker-up:
	docker compose -f docker-compose.yml up -d

docker-dev:
	docker compose up

docker-stop:
	docker compose stop

docker-clean:
	docker compose --profile callback down -v --rmi local

# Generate the API reference for third-party developers:
#   docs/en/openapi.yaml  — machine-readable OpenAPI 3.0 schema (Postman/Insomnia, SDK codegen)
#   docs/en/api.html      — self-contained, offline browsable reference (no token, no network)
# The HTML step needs Node.js/npx; the first run downloads @redocly/cli.
# LANGUAGE_CODE is "uk" (pbx/settings.py), so `manage.py spectacular` run plain
# would translate model verbose_name/help_text into Ukrainian in these
# "English" docs — force English explicitly for this generation.
api-docs:
	.python-venv/bin/python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pbx.settings'); django.setup(); from django.utils import translation; from django.core.management import call_command; translation.activate('en'); call_command('spectacular', file='docs/en/openapi.yaml')"
	npx --yes @redocly/cli build-docs docs/en/openapi.yaml -o docs/en/api.html

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

# Integration tests against a REAL Asterisk container (tests/integration/) —
# slower than `make test` (Asterisk boot + config reload), isolated stack,
# separate from the dev (docker-compose.yml) and mocked-test
# (docker-compose.test.yml) stacks. See docker-compose.integration.yml.
integration-build:
	docker compose -f docker-compose.integration.yml build

integration-test: integration-build
	docker compose -f docker-compose.integration.yml run --rm integration-test

integration-down:
	docker compose -f docker-compose.integration.yml down -v
