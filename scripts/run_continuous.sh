#!/bin/bash
# Continuous pipeline runner
# Usage: ./scripts/run_continuous.sh [interval_seconds]

set -a && source .env && set +a

INTERVAL=${1:-300}  # Default: 5 minutes

echo "Starting continuous pipeline (interval: ${INTERVAL}s)"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    echo "========================================"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting pipeline run"
    echo "========================================"

    # 1. Run main pipeline (ingest → cluster → tag → trending)
    python -m curious_now.cli pipeline

    # 2. Generate AI takeaways for new clusters
    echo ""
    echo "Generating AI takeaways..."
    CN_LLM_ADAPTER=${CN_LLM_ADAPTER:-claude-cli} python -m curious_now.cli generate-takeaways --limit 50

    # 3. Generate deep dives (Stage 3 enrichment)
    echo ""
    echo "Generating deep dives..."
    CN_LLM_ADAPTER=${CN_LLM_ADAPTER:-claude-cli} python -m curious_now.cli enrich-stage3 --limit 50

    # 4. Generate embeddings for semantic search (optional)
    # echo ""
    # echo "Generating embeddings..."
    # python -m curious_now.cli generate-embeddings --limit 50

    echo ""
    echo "Pipeline complete. Sleeping for ${INTERVAL}s..."
    echo ""
    sleep $INTERVAL
done
