# AlfredV Umbrella

Orchestrates AlfredV and product repos via Git submodules.

## Structure

```
umbrella/
├── alfredv/                          # AlfredV submodule (agents, MCP, dashboard, hooks)
├── ShopifyLightning/                 # ShopifyLightning submodule (first product)
├── smoke-tests/                      # Compatibility smoke tests (run against all products)
├── scripts/
│   ├── export-product.sh             # Export a product's Neo4j DB + Qdrant collection
│   └── import-product.sh             # Import into a dedicated instance
├── Makefile
├── docker-compose.yml
└── .github/workflows/
    ├── integration.yml               # AlfredV unit tests on push/PR
    └── compat-gate.yml               # Compatibility gate + auto-bump (scheduled daily)
```

Each product sits at the umbrella root alongside `alfredv/` — not nested inside a subdirectory.

## Quick Start

```bash
git clone --recurse-submodules https://github.com/azizhanazizoglu/umbrella.git
cd umbrella
make setup
```

## Product Structure

Every product repo must follow this layout:

```
MyProduct/
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
# 1. Create standalone repo (GitHub + local folder)
mkdir ~/Documents/Playground/MyProduct && cd ~/Documents/Playground/MyProduct
git init && git checkout -b main
# scaffold: .alfred/project.yaml, agent-docs/, src/, tests/, config/, pyproject.toml
git remote add origin https://github.com/you/MyProduct.git
git push -u origin main

# 2. Add as submodule at umbrella root (same level as alfredv/)
cd /path/to/umbrella
git submodule add https://github.com/you/MyProduct.git MyProduct
git commit -m "feat: add MyProduct submodule"
git push

# 3. Activate the product for AlfredV
alfred use ~/Documents/Playground/MyProduct
alfred status
```

The `.alfred/project.yaml` descriptor tells AlfredV the product's name, paths, Neo4j/Qdrant config, and GitHub repo. See [ShopifyLightning/.alfred/README.md](ShopifyLightning/.alfred/README.md) for the full schema.

## Commands

```bash
make setup               # Init submodules + install deps
make test-alfredv        # Run AlfredV unit tests
make smoke-test          # Run compatibility smoke tests (all products)
make integration         # AlfredV tests + smoke tests
make test-product        # Run active product tests (set PRODUCT=name)
make lint                # Lint all submodules

make services            # Start shared Neo4j + Qdrant + Dashboard
make services-dedicated  # Also start dedicated product DB instances (ports 7688/6335)
make services-down       # Stop all services

make export-product PRODUCT_PATH=/path/to/product  # Export product DB → data/exports/
make import-product PRODUCT_PATH=/path/to/product  # Import into dedicated instance
```

## Database Isolation — Shared vs Dedicated (E3 Hybrid)

By default, all products share one Neo4j and one Qdrant instance, each using a separate **database/collection** named after the product. This is local dev mode.

For handoff or production, a product can use its own dedicated DB instances:

**Step 1 — Start dedicated instances:**
```bash
make services-dedicated
# Adds: neo4j-product (port 7688) + qdrant-product (port 6335)
```

**Step 2 — Export from shared, import into dedicated:**
```bash
make export-product PRODUCT_PATH=/path/to/ShopifyLightning
make import-product PRODUCT_PATH=/path/to/ShopifyLightning
```

**Step 3 — Tell the product to use its own instance:**
```yaml
# ShopifyLightning/.alfred/project.yaml — add these 3 lines:
neo4j_uri: "bolt://localhost:7688"
qdrant_host: "localhost"
qdrant_port: 6335
```

From this point, all agent DB calls for ShopifyLightning route to the dedicated instance. AlfredV's own graph always stays on the shared instance.

## Git Workflow — Committing to AlfredV from Inside Umbrella

The `alfredv/` directory is a Git submodule — it is a full AlfredV git clone pinned to a specific commit.

**Option A — Work in the standalone AlfredV repo (recommended):**
```bash
# Make changes in the standalone repo
cd ~/Documents/Playground/AlfredV
git checkout -b improve/something
# ... edit files ...
git commit && git push
# Open PR to AlfredV main, merge it

# Back in umbrella — bump the submodule pointer
cd ~/Documents/Playground/umbrella
git submodule update --remote alfredv
git add alfredv
git commit -m "chore: bump alfredv to latest"
git push
```

The `compat-gate.yml` CI runs daily and auto-bumps if smoke tests pass. Manual bump is only needed for immediate updates.

**Option B — Edit inside the submodule directly:**
```bash
cd umbrella/alfredv
git checkout -b improve/something   # leave detached HEAD first
# ... edit files ...
git commit && git push origin improve/something
# Merge the branch to AlfredV main (via PR or directly)

# Back in umbrella root:
cd ..
git add alfredv
git commit -m "chore: bump alfredv to {sha}"
```

**Auto-bump CI (`compat-gate.yml`):**
- Runs daily at 06:00 UTC
- Checks if AlfredV upstream (`origin/main`) has new commits
- Runs all smoke tests + product tests
- If all pass → auto-commits `chore: bump alfredv to {sha}` in umbrella
- If any fail → opens a GitHub Issue in umbrella, blocks the bump

## CI

| Workflow | Trigger | What it does |
|---------|---------|-------------|
| `integration.yml` | Push to main / PR | Runs AlfredV unit tests |
| `compat-gate.yml` | Daily 06:00 UTC / push / manual | Detects upstream changes, runs smoke tests, auto-bumps submodule pointers if all pass |
