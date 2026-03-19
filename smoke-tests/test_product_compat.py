"""Smoke tests: verify AlfredV compatibility with each product submodule.

These tests run without live databases — they validate that:
1. Each product has a valid .alfred/project.yaml
2. AlfredV's config loader can merge product overrides
3. MCP server product_context resolves correctly
4. No import errors in AlfredV infrastructure
5. CLI commands work against product directories
6. Database name uniqueness across all products
7. Agent-docs structure is valid
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Umbrella root
UMBRELLA_ROOT = Path(__file__).resolve().parent.parent
ALFREDV_ROOT = UMBRELLA_ROOT / "alfredv"

# Add AlfredV src to path so we can import alfredv.config
sys.path.insert(0, str(ALFREDV_ROOT / "src"))
# Add MCP servers to path for product_context
sys.path.insert(0, str(ALFREDV_ROOT / ".claude" / "mcp-servers"))


REQUIRED_YAML_FIELDS = [
    "project_name",
    "src_path",
    "tests_path",
    "agent_docs_path",
    "neo4j_database",
    "qdrant_collection",
    "github_repo",
]


def discover_products() -> list[Path]:
    """Find all product submodules with .alfred/project.yaml."""
    products = []
    for child in UMBRELLA_ROOT.iterdir():
        if child.is_dir() and child.name != "alfredv" and child.name != ".git":
            project_yaml = child / ".alfred" / "project.yaml"
            if project_yaml.exists():
                products.append(child)
    return products


PRODUCTS = discover_products()
PRODUCT_IDS = [p.name for p in PRODUCTS]


@pytest.fixture(params=PRODUCTS, ids=PRODUCT_IDS)
def product_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture
def product_yaml(product_path: Path) -> dict:
    with open(product_path / ".alfred" / "project.yaml") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# YAML schema tests
# ---------------------------------------------------------------------------


def test_project_yaml_exists(product_path: Path) -> None:
    """Every product must have .alfred/project.yaml."""
    assert (product_path / ".alfred" / "project.yaml").exists()


def test_project_yaml_required_fields(product_yaml: dict) -> None:
    """project.yaml must contain all required fields."""
    for field in REQUIRED_YAML_FIELDS:
        assert field in product_yaml, f"Missing required field: {field}"
        assert product_yaml[field], f"Field '{field}' is empty"


def test_project_yaml_override_fields_valid(product_yaml: dict) -> None:
    """If optional override fields are set, they must be valid."""
    if uri := product_yaml.get("neo4j_uri"):
        assert uri.startswith("bolt://"), f"neo4j_uri must start with bolt://, got: {uri}"
    if port := product_yaml.get("qdrant_port"):
        assert isinstance(port, int) and 1024 <= port <= 65535, f"Invalid qdrant_port: {port}"


def test_project_yaml_database_name_format(product_yaml: dict) -> None:
    """Database names must be lowercase, alphanumeric with hyphens only."""
    import re

    db_name = product_yaml["neo4j_database"]
    assert re.match(r"^[a-z0-9][a-z0-9-]*$", db_name), (
        f"neo4j_database '{db_name}' must be lowercase alphanumeric with hyphens"
    )
    col_name = product_yaml["qdrant_collection"]
    assert re.match(r"^[a-z0-9][a-z0-9-]*$", col_name), (
        f"qdrant_collection '{col_name}' must be lowercase alphanumeric with hyphens"
    )


# ---------------------------------------------------------------------------
# Cross-product uniqueness
# ---------------------------------------------------------------------------


def test_database_names_unique_across_products() -> None:
    """No two products share a neo4j_database or qdrant_collection name."""
    neo4j_dbs: dict[str, str] = {}
    qdrant_cols: dict[str, str] = {}

    for product_dir in PRODUCTS:
        with open(product_dir / ".alfred" / "project.yaml") as f:
            cfg = yaml.safe_load(f)
        name = cfg["project_name"]
        db = cfg["neo4j_database"]
        col = cfg["qdrant_collection"]

        assert db not in neo4j_dbs, (
            f"neo4j_database '{db}' is shared by '{name}' and '{neo4j_dbs[db]}'"
        )
        assert col not in qdrant_cols, (
            f"qdrant_collection '{col}' is shared by '{name}' and '{qdrant_cols[col]}'"
        )
        neo4j_dbs[db] = name
        qdrant_cols[col] = name


# ---------------------------------------------------------------------------
# AlfredV config integration
# ---------------------------------------------------------------------------


def test_alfredv_config_loads(product_path: Path, product_yaml: dict, tmp_path: Path) -> None:
    """AlfredV config.py can load and merge product overrides."""
    from alfredv.config import DatabaseConfig, Settings, _apply_product_overrides

    settings = Settings()

    # Set up temp home with .alfred/active-product pointing to a temp product dir
    product_dir = tmp_path / "product"
    product_dir.mkdir()
    alfred_dir = product_dir / ".alfred"
    alfred_dir.mkdir()
    with open(alfred_dir / "project.yaml", "w") as f:
        yaml.dump(product_yaml, f)

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    home_alfred = home_dir / ".alfred"
    home_alfred.mkdir()
    (home_alfred / "active-product").write_text(str(product_dir))

    old_home = os.environ.get("HOME")
    try:
        os.environ["HOME"] = str(home_dir)
        _apply_product_overrides(settings)
    finally:
        if old_home:
            os.environ["HOME"] = old_home

    assert isinstance(settings.database, DatabaseConfig)


def test_alfredv_config_applies_overrides(
    product_path: Path, product_yaml: dict, tmp_path: Path
) -> None:
    """After loading product overrides, connection settings are applied."""
    from alfredv.config import Settings, _apply_product_overrides

    settings = Settings()

    product_dir = tmp_path / "product"
    product_dir.mkdir()
    alfred_dir = product_dir / ".alfred"
    alfred_dir.mkdir()
    # Add a neo4j_uri override to test that it gets applied
    overridden_yaml = dict(product_yaml)
    overridden_yaml["neo4j_uri"] = "bolt://custom-host:7687"
    with open(alfred_dir / "project.yaml", "w") as f:
        yaml.dump(overridden_yaml, f)

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    home_alfred = home_dir / ".alfred"
    home_alfred.mkdir()
    (home_alfred / "active-product").write_text(str(product_dir))

    old_home = os.environ.get("HOME")
    try:
        os.environ["HOME"] = str(home_dir)
        _apply_product_overrides(settings)
    finally:
        if old_home:
            os.environ["HOME"] = old_home

    assert settings.database.neo4j_uri == "bolt://custom-host:7687"


# ---------------------------------------------------------------------------
# MCP server product_context
# ---------------------------------------------------------------------------


def test_product_context_resolves(product_path: Path, product_yaml: dict, tmp_path: Path) -> None:
    """product_context.py resolves the product's DB settings."""
    product_context_path = ALFREDV_ROOT / ".claude" / "mcp-servers" / "product_context.py"
    if not product_context_path.exists():
        pytest.skip("product_context.py not present in this AlfredV version")

    from product_context import load_product_context

    # Set up temp home with .alfred/active-product pointing to actual product
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    home_alfred = home_dir / ".alfred"
    home_alfred.mkdir()
    (home_alfred / "active-product").write_text(str(product_path))

    old_home = os.environ.get("HOME")
    try:
        os.environ["HOME"] = str(home_dir)
        ctx = load_product_context()
    finally:
        if old_home:
            os.environ["HOME"] = old_home

    assert ctx is not None
    assert ctx.product_name == product_yaml["project_name"]
    assert ctx.neo4j_database == product_yaml["neo4j_database"]
    assert ctx.qdrant_collection == product_yaml["qdrant_collection"]


def test_product_context_has_required_attrs() -> None:
    """ProductContext dataclass has the expected fields."""
    product_context_path = ALFREDV_ROOT / ".claude" / "mcp-servers" / "product_context.py"
    if not product_context_path.exists():
        pytest.skip("product_context.py not present in this AlfredV version")

    import dataclasses

    from product_context import ProductContext

    field_names = {f.name for f in dataclasses.fields(ProductContext)}
    required_attrs = [
        "product_name", "product_path", "neo4j_uri", "neo4j_database",
        "qdrant_host", "qdrant_port", "qdrant_collection",
    ]
    for attr in required_attrs:
        assert attr in field_names, f"ProductContext missing field: {attr}"


# ---------------------------------------------------------------------------
# AlfredV imports
# ---------------------------------------------------------------------------


def test_alfredv_imports_clean() -> None:
    """AlfredV core modules import without errors."""
    import alfredv.config

    assert hasattr(alfredv.config, "get_settings")
    assert hasattr(alfredv.config, "load_settings")
    assert hasattr(alfredv.config, "Settings")


def test_alfredv_settings_class_has_database_field() -> None:
    """Settings must have a database field with expected sub-fields."""
    from alfredv.config import Settings

    settings = Settings()
    assert hasattr(settings, "database")
    db = settings.database
    assert hasattr(db, "neo4j_uri")
    assert hasattr(db, "qdrant_host")
    assert hasattr(db, "qdrant_port")


def test_alfredv_infrastructure_imports_clean() -> None:
    """Infrastructure modules import without errors."""
    infra_dir = ALFREDV_ROOT / "src" / "alfredv" / "infrastructure"
    if not infra_dir.exists():
        pytest.skip("infrastructure package not present")

    import alfredv.infrastructure

    assert alfredv.infrastructure is not None


# ---------------------------------------------------------------------------
# Product directory structure
# ---------------------------------------------------------------------------


def test_product_agent_docs_structure(product_path: Path, product_yaml: dict) -> None:
    """Product must have agent-docs/ with expected subdirectories."""
    agent_docs = product_path / product_yaml.get("agent_docs_path", "agent-docs/").rstrip("/")
    if not agent_docs.exists():
        pytest.skip(f"agent-docs not yet created at {agent_docs}")

    expected_subdirs = ["requirements", "architecture"]
    for subdir in expected_subdirs:
        assert (agent_docs / subdir).exists(), (
            f"Missing agent-docs/{subdir}/ — required for V-model pipeline"
        )


def test_product_src_directory_exists(product_path: Path, product_yaml: dict) -> None:
    """Product must have the source directory declared in project.yaml."""
    src = product_path / product_yaml.get("src_path", "src/").rstrip("/")
    assert src.exists(), f"Source directory not found at {src}"


# ---------------------------------------------------------------------------
# CLI smoke tests (alfred binary)
# ---------------------------------------------------------------------------


def _alfred_bin() -> str | None:
    """Find the alfred binary."""
    import shutil

    return shutil.which("alfred")


def test_cli_use_and_status(product_path: Path, product_yaml: dict, tmp_path: Path) -> None:
    """alfred use + alfred status works for each product."""
    alfred = _alfred_bin()
    if not alfred:
        pytest.skip("alfred CLI not on PATH")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    # alfred use
    result = subprocess.run(
        [alfred, "use", str(product_path)],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0, f"alfred use failed: {result.stderr}"
    assert product_yaml["project_name"] in result.stdout

    # alfred status
    result = subprocess.run(
        [alfred, "status"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0, f"alfred status failed: {result.stderr}"
    assert product_yaml["project_name"] in result.stdout
    assert product_yaml["neo4j_database"] in result.stdout


def test_cli_list_shows_products(tmp_path: Path) -> None:
    """alfred list discovers products when active product is set."""
    alfred = _alfred_bin()
    if not alfred:
        pytest.skip("alfred CLI not on PATH")
    if not PRODUCTS:
        pytest.skip("No products discovered")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    # Set first product as active so list scans the right parent
    first = PRODUCTS[0]
    subprocess.run(
        [alfred, "use", str(first)],
        capture_output=True, text=True, env=env, timeout=10,
    )

    result = subprocess.run(
        [alfred, "list"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0, f"alfred list failed: {result.stderr}"
    assert "Products in" in result.stdout


def test_cli_doctor_runs_without_crash(product_path: Path, tmp_path: Path) -> None:
    """alfred doctor runs without panicking (services may be down)."""
    alfred = _alfred_bin()
    if not alfred:
        pytest.skip("alfred CLI not on PATH")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    # Set product
    subprocess.run(
        [alfred, "use", str(product_path)],
        capture_output=True, text=True, env=env, timeout=10,
    )

    # Doctor should run without crashing — exit code 0 even if services are down
    result = subprocess.run(
        [alfred, "doctor"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert result.returncode == 0, f"alfred doctor crashed: {result.stderr}"
    assert "Active product:" in result.stdout


def test_cli_init_rejects_duplicate_db(product_path: Path, product_yaml: dict, tmp_path: Path) -> None:
    """alfred init rejects a product name that collides with existing DB name."""
    alfred = _alfred_bin()
    if not alfred:
        pytest.skip("alfred CLI not on PATH")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    # Try to init a product with the same name as an existing one in the same parent
    parent = str(product_path.parent)
    existing_name = product_yaml["project_name"]

    result = subprocess.run(
        [alfred, "init", existing_name, "--parent", parent],
        capture_output=True, text=True, env=env, timeout=10,
    )
    # Should fail — either "already initialized" or "DB name collision"
    assert result.returncode != 0, (
        f"alfred init should reject duplicate name '{existing_name}'"
    )


# ---------------------------------------------------------------------------
# State file schema validation (if state.json exists)
# ---------------------------------------------------------------------------


def test_state_json_schema_if_exists(product_path: Path) -> None:
    """If .alfred/state.json exists, validate its schema."""
    state_file = product_path / ".alfred" / "state.json"
    if not state_file.exists():
        pytest.skip("No state.json (product hasn't exported yet)")

    with open(state_file) as f:
        state = json.load(f)

    assert "schema_version" in state, "state.json missing schema_version"
    assert "product" in state, "state.json missing product field"
    assert "nodes" in state, "state.json missing nodes field"

    # Nodes should have expected categories
    for key in ["features", "tasks"]:
        assert key in state["nodes"], f"state.json nodes missing '{key}'"
