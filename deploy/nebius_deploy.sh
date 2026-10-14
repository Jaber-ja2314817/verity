#!/usr/bin/env bash
set -euo pipefail
source .env
: "${IMAGE:?set IMAGE=ghcr.io/<user>/verity:<tag>}"
NAME="${NAME:-verity}"
PLATFORM="${PLATFORM:-cpu-d3}"
PRESET="${PRESET:?run: nebius compute platform list --parent-id \$PROJECT_ID --format json  and pick the smallest cpu-d3 preset}"

ARGS=(--name "$NAME" --image "$IMAGE"
  --platform "$PLATFORM" --preset "$PRESET"
  --container-port 8000
  --auth none
  --disk-size "${DISK_SIZE:-32Gi}"
  --env "NEBIUS_API_KEY=$NEBIUS_API_KEY"
  --env "NEBIUS_BASE_URL=$NEBIUS_BASE_URL"
  --env "MODEL_FAST=$MODEL_FAST"
  --env "MODEL_JUDGE=$MODEL_JUDGE"
  --env "TAVILY_API_KEY=$TAVILY_API_KEY"
  --env "STRUCTURED_MODE_FAST=${STRUCTURED_MODE_FAST:-tool_forced}"
  --env "STRUCTURED_MODE_JUDGE=${STRUCTURED_MODE_JUDGE:-tool_forced}"
  --env "DATA_DIR=/data")

if [[ "${DRY_RUN:-1}" == "1" ]]; then
  nebius ai endpoint create "${ARGS[@]}" --dry-run > /dev/null && echo "Dry run OK. Run with DRY_RUN=0 to create."
  exit 0
fi
# Output is discarded: endpoint specs contain the env values (keys).
nebius ai endpoint create "${ARGS[@]}" > /dev/null
ID=$(nebius ai endpoint get-by-name --name "$NAME" --format json | jq -r '.metadata.id')
URL=$(nebius ai endpoint get "$ID" --format json | jq -r '.status.public_endpoints[] | select(startswith("https://"))' | head -1)
echo "Endpoint ID: $ID"
echo "URL: $URL"
