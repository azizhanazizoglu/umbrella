PRODUCT ?=
PRODUCT_PATH ?=

.PHONY: setup test-alfredv test-product smoke-test lint services services-down services-dedicated integration export-product import-product

setup:
	git submodule update --init --recursive
	cd alfredv && uv sync
ifdef PRODUCT
	cd products/$(PRODUCT) && uv sync
endif

test-alfredv:
	cd alfredv && uv run python -m pytest tests/ -v

test-product:
ifndef PRODUCT
	$(error PRODUCT is not set. Usage: make test-product PRODUCT=my-product)
endif
	cd products/$(PRODUCT) && uv run python -m pytest tests/ -v

lint:
	cd alfredv && uv run ruff check .
ifdef PRODUCT
	cd products/$(PRODUCT) && uv run ruff check .
endif

services:
	docker compose up -d

services-dedicated:
	docker compose --profile dedicated up -d

services-down:
	docker compose --profile dedicated down

smoke-test:
	cd alfredv && uv run python -m pytest ../smoke-tests/ -v

integration: test-alfredv smoke-test
ifdef PRODUCT
	uv run python -m pytest tests/integration/ -v --product=$(PRODUCT)
endif

export-product:
ifndef PRODUCT_PATH
	$(error PRODUCT_PATH is not set. Usage: make export-product PRODUCT_PATH=/path/to/product)
endif
	./scripts/export-product.sh $(PRODUCT_PATH)

import-product:
ifndef PRODUCT_PATH
	$(error PRODUCT_PATH is not set. Usage: make import-product PRODUCT_PATH=/path/to/product)
endif
	./scripts/import-product.sh $(PRODUCT_PATH)
