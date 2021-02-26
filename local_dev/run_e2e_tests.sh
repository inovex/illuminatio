#!/usr/bin/env bash

# Abort if any of the following commands fails or variables are undefined
set -eu

# default DOCKER_REGISTRY to the docker bind address and port if using docker driver
if [ "$(minikube config get driver)" = "docker" ]; then
  DOCKER_REGISTRY="${DOCKER_REGISTRY:-$(docker port minikube 5000)}"
else
  # otherwise default to the minikube IP and port 5000
  DOCKER_REGISTRY="${DOCKER_REGISTRY:-"$(minikube ip):5000"}"
fi

ILLUMINATIO_IMAGE="${DOCKER_REGISTRY}/illuminatio-runner:dev"

docker build -t "${ILLUMINATIO_IMAGE}" .

# Use minikube docker daemon to push to the insecure registry
counter=0
while ! docker push "${ILLUMINATIO_IMAGE}" &> /dev/null; do
  if [[ "$counter" -gt 25 ]]; then
       echo "Error: could not push image \'${ILLUMINATIO_IMAGE}\" to registry"
       exit 1
  fi
  echo "Wait for docker regsitry to become ready"
  counter=$((counter+1))
  sleep 5
done

if [[ -n "${CI:-}" ]];
then
  echo "Prepull: ${ILLUMINATIO_IMAGE} to ensure image is available"
  sudo docker pull "${ILLUMINATIO_IMAGE}"
fi

coverage run setup.py test --addopts="-m e2e"
