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

    # 1. Run main pipeline (ingest → hydrate → cluster → tag → trending)
    python -m curious_now.cli pipeline \
        --hydrate-paper-text \
        --hydrate-article-text

    # 2. Generate AI takeaways (1-liner summaries) for new clusters
    echo ""
    echo "Generating takeaways..."
    CN_LLM_ADAPTER=${CN_LLM_ADAPTER:-claude-cli} python -m curious_now.cli generate-takeaways --limit 50

    # 3. Enrich stage 3: deep dives for papers, news summaries for articles
    echo ""
    echo "Enriching clusters (deep dives + news summaries)..."
    CN_LLM_ADAPTER=${CN_LLM_ADAPTER:-claude-cli} python -m curious_now.cli enrich-stage3 --limit 100

    # 4. Promote pending clusters that now meet readiness criteria
    echo ""
    echo "Promoting ready clusters..."
    python -m curious_now.cli promote-clusters

    # 5. Generate embeddings for semantic search (optional)
    # echo ""
    # echo "Generating embeddings..."
    # python -m curious_now.cli generate-embeddings --limit 50

    echo ""
    echo "Pipeline complete. Sleeping for ${INTERVAL}s..."
    echo ""
    sleep $INTERVAL
done
