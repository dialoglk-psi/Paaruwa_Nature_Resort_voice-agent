#!/usr/bin/env bash
set -euo pipefail

IMAGE="psi-nprod-registry.tencentcloudcr.com/paaruwa-agent/paaruwa-resort-agent:v2"

echo "==> Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" .
echo "==> Build complete."

echo "==> Pushing image to Docker Hub: ${IMAGE}"
docker push "${IMAGE}"
echo "==> Push complete."

echo "==> Done. Image available at: ${IMAGE}"
