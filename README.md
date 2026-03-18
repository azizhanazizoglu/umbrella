# AlfredV Umbrella

Orchestrates AlfredV and product repos via Git submodules.

## Structure

```
umbrella/
├── alfredv/          # AlfredV submodule (agents, MCP servers, dashboard, hooks)
├── products/         # Product repo submodules go here
│   └── .gitkeep
├── Makefile          # Setup, test, lint, integration commands
├── docker-compose.yml
└── .github/workflows/integration.yml
```

## Quick Start

```bash
git clone --recurse-submodules https://github.com/azizhanazizoglu/umbrella.git
cd umbrella
make setup
```

## Adding a Product

```bash
git submodule add https://github.com/you/my-product.git products/my-product
```

The product must have a `.alfred/project.yaml` descriptor. See the AlfredV repo for schema docs.

## Commands

```bash
make setup          # Init submodules + install deps
make test-alfredv   # Run AlfredV tests
make test-product   # Run active product tests (set PRODUCT=name)
make lint           # Lint all submodules
make services       # Start Neo4j + Qdrant + Dashboard
make services-down  # Stop all services
```
