#!/usr/bin/env bash
# abort if any of the following commands fails or variables are undefined
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
    --container-runtime=containerd \
    --bootstrapper=kubeadm \
    --host-only-cidr=172.17.17.1/24 \
    --insecure-registry=localhost:5000 \
    --kubernetes-version="${KUBERNETES_VERSION}"

minikube addons enable registry

if [[ -n "${CI:-}" ]];
then
    sudo chown -R travis: /home/travis/.minikube/
fi

# Configure containerd to use the local registry
if [[ -n "${CI:-}" ]];
then
    sudo mkdir -p /etc/containerd
    sudo tee /etc/containerd/config.toml <<EOF
[plugins.cri.registry.mirrors]
  [plugins.cri.registry.mirrors."localhost"]
    endpoint = ["http://localhost:5000"]
EOF

else
    minikube ssh <<EOF
# the following commands are executed inside the minikube vm
# Add the following lines -> see https://github.com/kubernetes/minikube/issues/3444
sudo sed -i '56i\          endpoint = ["http://localhost:5000"]' /etc/containerd/config.toml
sudo sed -i '56i\       [plugins.cri.registry.mirrors."localhost"]' /etc/containerd/config.toml
# Finally restart the containerd service
sudo systemctl restart containerd
exit
EOF
fi
