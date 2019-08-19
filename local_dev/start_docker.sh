#!/usr/bin/env bash
#abort if any of the following commands fails or variables are undefined
set -eu

#setup minikube
minikube delete
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
    --insecure-registry=localhost:5000

#setup the minikube docker registry and calico
minikube addons enable registry
kubectl apply -f https://docs.projectcalico.org/v3.8/getting-started/kubernetes/installation/hosted/kubernetes-datastore/calico-networking/1.7/calico.yaml
kubectl apply -f local_dev/docker-registry.yml
