#!/usr/bin/env bash
# Abort if any of the following commands fails or variables are undefined
set -eu

KUBERNETES_VERSION="${KUBERNETES_VERSION:-stable}"
CALICO_VERSION="${CALICO_VERSION:-v3.8}"

# Setup minikube
minikube delete
minikube config set embed-certs true
minikube start \
    --memory 4096 \
    --cpus 2 \
    --cni=calico \
    --container-runtime=docker \
    --bootstrapper=kubeadm \
    --host-only-cidr=172.17.17.1/24 \
    --kubernetes-version="${KUBERNETES_VERSION}"

# Setup the minikube docker registry and calico
minikube addons enable registry

if [[ -n "${CI:-}" ]];
then
    sudo chown -R travis: /home/travis/.minikube/
fi
