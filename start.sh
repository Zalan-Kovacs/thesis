#!/bin/bash
set -e

trap "docker compose down" EXIT INT TERM

echo "Starting Containers..."
docker compose up -d --build

echo "Waiting for OpenSearch..."
until curl -s http://localhost:9200 > /dev/null; do
    sleep 2
done
echo "OpenSearch is running."

echo "Pipeline and indeces check / initialization..."
docker compose exec -T backend python -m src.backend.init_opensearch

echo "System is ready. Logs:"
docker compose logs -f