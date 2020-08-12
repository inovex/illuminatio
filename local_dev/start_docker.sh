#!/usr/bin/env bash
# Abort if any of the following commands fails or variables are undefined
set -eu

KUBERNETES_VERSION="${KUBERNETES_VERSION:-stable}"

# Setup minikube, requires minikube >= 1.12.1
minikube delete
minikube config set embed-certs true
minikube start \
    --cni=calico \
    --container-runtime=docker \
    --host-only-cidr=172.17.17.1/24 \
    --kubernetes-version="${KUBERNETES_VERSION}"

# Setup the minikube docker registry and calico
minikube addons enable registry

if [[ -n "${CI:-}" ]];
then
    sudo chown -R travis: /home/travis/.minikube/
fi
