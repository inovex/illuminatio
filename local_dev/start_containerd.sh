#!/usr/bin/env bash
# abort if any of the following commands fails or variables are undefined
set -eu

CALICO_VERSION="${CALICO_VERSION:-v3.8}"

kind create cluster --config local_dev/kind.yaml --wait=120s
kubectl cluster-info --context kind-kind

kubectl apply -f "https://docs.projectcalico.org/${CALICO_VERSION}/getting-started/kubernetes/installation/hosted/kubernetes-datastore/calico-networking/1.7/calico.yaml"

# Prevent a race condition
sleep 5

kubectl -n kube-system wait po -l k8s-app=calico-node --for=condition=Ready --timeout=120s
