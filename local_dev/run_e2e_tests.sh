#!/usr/bin/env bash

# Abort if any of the following commands fails or variables are undefined
set -eu

# Default DOCKER_REGISTRY to the docker bind port if using docker driver
if [ "$(minikube config get driver)" = "docker" ]; then
  : ${DOCKER_REGISTRY:=$(docker port minikube 5000)}
else
# otherwise default it to port 5000 ouf the minikube IP
  : ${DOCKER_REGISTRY:="$(minikube ip):5000"}
fi

ILLUMINATIO_IMAGE="${DOCKER_REGISTRY}/illuminatio-runner:dev"

docker build -t "${ILLUMINATIO_IMAGE}" .

# Use minikube docker daemon to push to the insecure registry

docker push "${ILLUMINATIO_IMAGE}"

if [[ -n "${CI:-}" ]];
then
  echo "Prepull: ${ILLUMINATIO_IMAGE} to ensure image is available"
  # If crictl is not installed e.g. only Docker
  sudo crictl pull "${ILLUMINATIO_IMAGE}" || true
  sudo docker pull "${ILLUMINATIO_IMAGE}"
fi

if ! coverage run setup.py test --addopts="-m e2e";
then
  kubectl -n illuminatio get po -o yaml
fi
