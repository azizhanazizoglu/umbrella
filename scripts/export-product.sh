#!/usr/bin/env bash
# Export a product's Neo4j database + Qdrant collection to data/exports/<product>/
#
# Usage: ./scripts/export-product.sh <product-path>
#   e.g.: ./scripts/export-product.sh /home/aziz/Documents/Playground/ShopifyLightning
#   or:   make export-product PRODUCT_PATH=/home/aziz/Documents/Playground/ShopifyLightning
#
# Reads project_name, neo4j_database, qdrant_collection from .alfred/project.yaml.
# Exports:
#   data/exports/<product>/neo4j/   — Cypher dump of the product's Neo4j database
#   data/exports/<product>/qdrant/  — Qdrant snapshot of the product's collection

set -euo pipefail

PRODUCT_PATH="${1:?Usage: $0 <product-path>}"
PROJECT_YAML="$PRODUCT_PATH/.alfred/project.yaml"

if [[ ! -f "$PROJECT_YAML" ]]; then
    echo "ERROR: $PROJECT_YAML not found" >&2
    exit 1
fi

# Parse project.yaml (requires yq or python+yaml)
parse_yaml() {
    python3 -c "
import yaml, sys
with open('$PROJECT_YAML') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('$1', '$2'))
"
}

PRODUCT_NAME=$(parse_yaml project_name unknown)
NEO4J_DB=$(parse_yaml neo4j_database neo4j)
QDRANT_COLLECTION=$(parse_yaml qdrant_collection project-docs)

# Source Neo4j connection (shared instance by default)
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-devpassword}"

# Source Qdrant connection
QDRANT_HOST="${QDRANT_HOST:-localhost}"
QDRANT_PORT="${QDRANT_PORT:-6333}"

EXPORT_DIR="data/exports/$PRODUCT_NAME"
mkdir -p "$EXPORT_DIR/neo4j" "$EXPORT_DIR/qdrant"

echo "=== Exporting product: $PRODUCT_NAME ==="
echo "  Neo4j database: $NEO4J_DB"
echo "  Qdrant collection: $QDRANT_COLLECTION"
echo "  Export dir: $EXPORT_DIR"
echo ""

# ── Neo4j export ─────────────────────────────────────────────────────
echo "--- Neo4j: exporting database '$NEO4J_DB' via Cypher APOC ---"

# Use cypher-shell to dump all nodes and relationships from the product database
docker compose exec -T neo4j cypher-shell \
    -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    -d "$NEO4J_DB" \
    --format plain \
    "CALL apoc.export.cypher.all(null, {stream: true}) YIELD cypherStatements RETURN cypherStatements" \
    > "$EXPORT_DIR/neo4j/dump.cypher" 2>/dev/null || {

    # Fallback: plain Cypher export without APOC
    echo "  APOC not available — falling back to manual Cypher export"
    docker compose exec -T neo4j cypher-shell \
        -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
        -d "$NEO4J_DB" \
        --format plain \
        "MATCH (n) RETURN n LIMIT 0" > /dev/null 2>&1 || {
        echo "  WARNING: Cannot connect to Neo4j or database '$NEO4J_DB' does not exist"
        echo "  Skipping Neo4j export"
        echo "" > "$EXPORT_DIR/neo4j/dump.cypher"
    }

    # Export nodes
    docker compose exec -T neo4j cypher-shell \
        -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
        -d "$NEO4J_DB" \
        --format plain \
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props" \
        > "$EXPORT_DIR/neo4j/nodes.json" 2>/dev/null || true

    # Export relationships
    docker compose exec -T neo4j cypher-shell \
        -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
        -d "$NEO4J_DB" \
        --format plain \
        "MATCH (a)-[r]->(b) RETURN labels(a) AS from_labels, properties(a) AS from_props, type(r) AS rel_type, properties(r) AS rel_props, labels(b) AS to_labels, properties(b) AS to_props" \
        > "$EXPORT_DIR/neo4j/relationships.json" 2>/dev/null || true
}

echo "  Neo4j export → $EXPORT_DIR/neo4j/"

# ── Qdrant export ────────────────────────────────────────────────────
echo "--- Qdrant: creating snapshot of collection '$QDRANT_COLLECTION' ---"

SNAPSHOT_RESPONSE=$(curl -s -X POST \
    "http://${QDRANT_HOST}:${QDRANT_PORT}/collections/${QDRANT_COLLECTION}/snapshots" 2>/dev/null) || {
    echo "  WARNING: Cannot connect to Qdrant or collection '$QDRANT_COLLECTION' does not exist"
    echo "  Skipping Qdrant export"
    SNAPSHOT_RESPONSE=""
}

if [[ -n "$SNAPSHOT_RESPONSE" ]]; then
    SNAPSHOT_NAME=$(python3 -c "
import json, sys
try:
    data = json.loads('''$SNAPSHOT_RESPONSE''')
    print(data.get('result', {}).get('name', ''))
except:
    print('')
")

    if [[ -n "$SNAPSHOT_NAME" ]]; then
        curl -s -o "$EXPORT_DIR/qdrant/${QDRANT_COLLECTION}.snapshot" \
            "http://${QDRANT_HOST}:${QDRANT_PORT}/collections/${QDRANT_COLLECTION}/snapshots/${SNAPSHOT_NAME}"
        echo "  Qdrant snapshot → $EXPORT_DIR/qdrant/${QDRANT_COLLECTION}.snapshot"
    else
        echo "  WARNING: Snapshot creation returned no name — collection may be empty"
    fi
fi

echo ""
echo "=== Export complete: $EXPORT_DIR ==="
ls -lh "$EXPORT_DIR/neo4j/" "$EXPORT_DIR/qdrant/" 2>/dev/null
