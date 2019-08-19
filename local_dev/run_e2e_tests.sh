#!/usr/bin/env bash

#abort if any of the following commands fails or variables are undefined
set -eu

#use local docker daemon to build
unset DOCKER_TLS_VERIFY
unset DOCKER_HOST
unset DOCKER_CERT_PATH
unset DOCKER_API_VERSION

ILLUMNATIO_IMAGE="$(minikube ip):5000/illuminatio-runner:dev"

docker build -t "${ILLUMNATIO_IMAGE}" -f illuminatio-runner.dockerfile .

# Use minikube docker daemon to push to the insecure registry
eval "$(minikube docker-env)"
if docker images "${ILLUMNATIO_IMAGE}" | grep "${ILLUMNATIO_IMAGE}"
then
  docker rmi "${ILLUMNATIO_IMAGE}"
fi

until docker push "${ILLUMNATIO_IMAGE}"
do
  sleep 1
done

python setup.py test --addopts="-m e2e"
