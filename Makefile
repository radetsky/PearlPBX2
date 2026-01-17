.PHONY: test test-coverage test-quick test-app test-build test-down

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
