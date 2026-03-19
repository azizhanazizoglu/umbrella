#!/usr/bin/env bash
# Import a product's data from data/exports/<product>/ into a dedicated instance.
#
# Usage: ./scripts/import-product.sh <product-path> [--target-neo4j bolt://localhost:7688] [--target-qdrant localhost:6335]
#   e.g.: ./scripts/import-product.sh /home/aziz/Documents/Playground/ShopifyLightning
#   or:   make import-product PRODUCT_PATH=/home/aziz/Documents/Playground/ShopifyLightning
#
# Prerequisites:
#   - Dedicated instances running: docker compose --profile dedicated up -d
#   - Export completed: ./scripts/export-product.sh <product-path>
#
# After import, add to product's .alfred/project.yaml:
#   neo4j_uri: "bolt://localhost:7688"
#   qdrant_host: "localhost"
#   qdrant_port: 6335

set -euo pipefail

PRODUCT_PATH="${1:?Usage: $0 <product-path> [--target-neo4j URI] [--target-qdrant HOST:PORT]}"
shift
PROJECT_YAML="$PRODUCT_PATH/.alfred/project.yaml"

if [[ ! -f "$PROJECT_YAML" ]]; then
    echo "ERROR: $PROJECT_YAML not found" >&2
    exit 1
fi

# Defaults — dedicated instance ports from docker-compose.yml
TARGET_NEO4J_URI="bolt://localhost:7688"
TARGET_NEO4J_USER="neo4j"
TARGET_NEO4J_PASSWORD="devpassword"
TARGET_QDRANT_HOST="localhost"
TARGET_QDRANT_PORT="6335"

# Parse optional args
while [[ $# -gt 0 ]]; do
    case $1 in
        --target-neo4j) TARGET_NEO4J_URI="$2"; shift 2;;
        --target-qdrant)
            TARGET_QDRANT_HOST="${2%%:*}"
            TARGET_QDRANT_PORT="${2##*:}"
            shift 2;;
        *) echo "Unknown arg: $1" >&2; exit 1;;
    esac
done

# Parse project.yaml
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

EXPORT_DIR="data/exports/$PRODUCT_NAME"

if [[ ! -d "$EXPORT_DIR" ]]; then
    echo "ERROR: Export directory $EXPORT_DIR not found. Run export-product.sh first." >&2
    exit 1
fi

echo "=== Importing product: $PRODUCT_NAME ==="
echo "  Target Neo4j: $TARGET_NEO4J_URI (database: $NEO4J_DB)"
echo "  Target Qdrant: $TARGET_QDRANT_HOST:$TARGET_QDRANT_PORT (collection: $QDRANT_COLLECTION)"
echo "  Source: $EXPORT_DIR"
echo ""

# ── Neo4j import ─────────────────────────────────────────────────────
echo "--- Neo4j: importing into database '$NEO4J_DB' ---"

# Extract host:port from bolt URI for docker exec targeting
NEO4J_CONTAINER="neo4j-product"

# Create the database if it doesn't exist (Community edition uses default 'neo4j' db)
if [[ -f "$EXPORT_DIR/neo4j/dump.cypher" ]] && [[ -s "$EXPORT_DIR/neo4j/dump.cypher" ]]; then
    docker compose --profile dedicated exec -T "$NEO4J_CONTAINER" cypher-shell \
        -u "$TARGET_NEO4J_USER" -p "$TARGET_NEO4J_PASSWORD" \
        -d "$NEO4J_DB" \
        < "$EXPORT_DIR/neo4j/dump.cypher" 2>/dev/null && \
        echo "  Neo4j Cypher dump imported" || \
        echo "  WARNING: Cypher import had errors (some statements may have succeeded)"
elif [[ -f "$EXPORT_DIR/neo4j/nodes.json" ]]; then
    echo "  WARNING: Only JSON export available — manual import needed"
    echo "  Files: $EXPORT_DIR/neo4j/nodes.json, $EXPORT_DIR/neo4j/relationships.json"
else
    echo "  No Neo4j export data found — skipping"
fi

# ── Qdrant import ────────────────────────────────────────────────────
echo "--- Qdrant: restoring collection '$QDRANT_COLLECTION' ---"

SNAPSHOT_FILE="$EXPORT_DIR/qdrant/${QDRANT_COLLECTION}.snapshot"

if [[ -f "$SNAPSHOT_FILE" ]]; then
    # Upload snapshot to restore the collection
    curl -s -X POST \
        "http://${TARGET_QDRANT_HOST}:${TARGET_QDRANT_PORT}/collections/${QDRANT_COLLECTION}/snapshots/upload" \
        -H "Content-Type: multipart/form-data" \
        -F "snapshot=@${SNAPSHOT_FILE}" > /dev/null 2>&1 && \
        echo "  Qdrant collection restored from snapshot" || \
        echo "  WARNING: Qdrant snapshot restore failed"
else
    echo "  No Qdrant snapshot found — skipping"
fi

echo ""
echo "=== Import complete ==="
echo ""
echo "Next step: add these lines to $PROJECT_YAML:"
echo "  neo4j_uri: \"$TARGET_NEO4J_URI\""
echo "  qdrant_host: \"$TARGET_QDRANT_HOST\""
echo "  qdrant_port: $TARGET_QDRANT_PORT"
