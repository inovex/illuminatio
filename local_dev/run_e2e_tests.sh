#!/usr/bin/env bash

# Abort if any of the following commands fails or variables are undefined
set -eu

DOCKER_REGISTRY=${DOCKER_REGISTRY:-"localhost"}
ILLUMINATIO_IMAGE="${DOCKER_REGISTRY}:5000/illuminatio-runner:dev"

docker build -t "${ILLUMINATIO_IMAGE}" -f illuminatio-runner.dockerfile .

# Use minikube docker daemon to push to the insecure registry

docker push "${ILLUMINATIO_IMAGE}"

python setup.py test --addopts="-m e2e"
