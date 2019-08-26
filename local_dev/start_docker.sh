#!/usr/bin/env bash
# Abort if any of the following commands fails or variables are undefined
set -eu

KUBERNETES_VERSION="${KUBERNETES_VERSION:-v1.15.0}"
CALICO_VERSION="${CALICO_VERSION:-v3.8}"

# Setup minikube
minikube delete
minikube config set embed-certs true
minikube start \
    --memory 4096 \
    --cpus 4 \
    --network-plugin=cni \
    --container-runtime=docker \
    --extra-config=kubelet.network-plugin=cni \
    --extra-config=kubelet.pod-cidr=192.168.0.0/16 \
    --extra-config=controller-manager.allocate-node-cidrs=true \
    --extra-config=controller-manager.cluster-cidr=192.168.0.0/16 \
    --bootstrapper=kubeadm \
    --host-only-cidr=172.17.17.1/24 \
    --insecure-registry=localhost:5000 \
    --kubernetes-version="${KUBERNETES_VERSION}"

# Setup the minikube docker registry and calico
minikube addons enable registry

if [[ -n "${CI:-}" ]];
then
    sudo chown -R travis: /home/travis/.minikube/
fi

kubectl apply -f "https://docs.projectcalico.org/${CALICO_VERSION}/getting-started/kubernetes/installation/hosted/kubernetes-datastore/calico-networking/1.7/calico.yaml"
kubectl apply -f local_dev/docker-registry.yml
