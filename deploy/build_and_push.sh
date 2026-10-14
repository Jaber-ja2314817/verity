#!/usr/bin/env bash
set -euo pipefail
: "${GHCR_USER:?set GHCR_USER}"; : "${GHCR_TOKEN:?set GHCR_TOKEN}"
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="ghcr.io/${GHCR_USER}/verity:${TAG}"
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
docker buildx build --platform linux/amd64 -t "$IMAGE" --push .
echo "Pushed $IMAGE"
