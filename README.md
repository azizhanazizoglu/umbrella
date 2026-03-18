# AlfredV Umbrella

Orchestrates AlfredV and product repos via Git submodules.

## Structure

```
umbrella/
├── alfredv/                    # AlfredV submodule (agents, MCP, dashboard, hooks)
├── products/
│   └── shopify-product/        # ShopifyProduct submodule (first product)
├── Makefile
├── docker-compose.yml
└── .github/workflows/integration.yml
```

## Quick Start

```bash
git clone --recurse-submodules https://github.com/azizhanazizoglu/umbrella.git
cd umbrella
make setup
```

## Product Structure

Every product repo must follow this layout:

```
my-product/
├── .alfred/
│   ├── project.yaml        # AlfredV product descriptor (required)
│   └── README.md
├── agent-docs/
│   ├── requirements/       # FR/NFR docs (requirements-analyst output)
│   ├── architecture/       # Architecture docs (architect output)
│   └── userstories/        # User stories (PM → requirements-analyst handoff)
├── src/
│   └── {product_name}/     # Python package
├── tests/                  # Pytest tests (test-engineer output)
├── config/
│   ├── .env.example
│   └── settings.yaml.example
├── pyproject.toml
└── README.md
```

**Key rule:** `agent-docs/` lives in the product repo, not in AlfredV. All V-model artifacts (requirements, architecture, TDSPs) are product-specific and travel with the product.

## Adding a New Product

```bash
# 1. Create and scaffold the product repo
mkdir my-product && cd my-product
git init && git checkout -b main
# ... create .alfred/project.yaml, agent-docs/, src/, tests/, config/, pyproject.toml

# 2. Add as submodule in umbrella
cd /path/to/umbrella
git submodule add https://github.com/you/my-product.git products/my-product

# 3. Activate the product for AlfredV
alfred use /path/to/my-product
alfred status
```

The `.alfred/project.yaml` descriptor tells AlfredV the product's name, paths, Neo4j/Qdrant config, and GitHub repo for issue tracking. See [ShopifyProduct](products/shopify-product/.alfred/README.md) for the full schema.

## Commands

```bash
make setup          # Init submodules + install deps
make test-alfredv   # Run AlfredV tests
make test-product   # Run active product tests (set PRODUCT=name)
make lint           # Lint all submodules
make services       # Start Neo4j + Qdrant + Dashboard
make services-down  # Stop all services
```
