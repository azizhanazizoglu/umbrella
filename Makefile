PRODUCT ?=

.PHONY: setup test-alfredv test-product lint services services-down integration

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

services-down:
	docker compose down

integration:
ifdef PRODUCT
	uv run python -m pytest tests/integration/ -v --product=$(PRODUCT)
else
	@echo "No PRODUCT set — skipping product integration tests"
	@echo "Usage: make integration PRODUCT=my-product"
endif
