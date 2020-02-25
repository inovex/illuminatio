#!/usr/bin/env bash

# Abort if any of the following commands fails or variables are undefined
set -eu

DOCKER_REGISTRY=${DOCKER_REGISTRY:-"localhost"}
ILLUMINATIO_IMAGE="${DOCKER_REGISTRY}:5000/illuminatio-runner:dev"

if command -v img > /dev/null;
then
  img build -t "${ILLUMINATIO_IMAGE}" -f illuminatio-runner.dockerfile .
  img push --insecure-registry "${ILLUMINATIO_IMAGE}"
else
  docker build -t "${ILLUMINATIO_IMAGE}" -f illuminatio-runner.dockerfile .
fi
# Use minikube docker daemon to push to the insecure registry

docker push "${ILLUMINATIO_IMAGE}"

if [[ -n "${CI:-}" ]];
then
  echo "Prepull: ${ILLUMINATIO_IMAGE} to ensure image is available"
  # If crictl is not installed e.g. only Docker
  sudo crictl pull "${ILLUMINATIO_IMAGE}" || true
  sudo docker pull "${ILLUMINATIO_IMAGE}"
fi

if ! python setup.py test --addopts="-m e2e";
then
  kubectl -n illuminatio get po -o yaml
fi
