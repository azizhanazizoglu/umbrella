"""Smoke tests: verify AlfredV compatibility with each product submodule.

These tests run without live databases — they validate that:
1. Each product has a valid .alfred/project.yaml
2. AlfredV's config loader can merge product overrides
3. MCP server product_context resolves correctly
4. No import errors in AlfredV infrastructure
"""

from __future__ import annotations

import os
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


def test_alfredv_imports_clean() -> None:
    """AlfredV core modules import without errors."""
    import alfredv.config

    assert hasattr(alfredv.config, "get_settings")
    assert hasattr(alfredv.config, "load_settings")
    assert hasattr(alfredv.config, "Settings")
