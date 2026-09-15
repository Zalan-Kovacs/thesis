#!/bin/bash

docker compose up -d

echo "Waiting for OpenSearch..."
until curl -s http://localhost:9200 > /dev/null; do
    sleep 2
done
echo "OpenSearch is running."

cd backend
uv run fastapi dev src/backend/main.py &
BACKEND_PID=$!
cd ..

cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

wait