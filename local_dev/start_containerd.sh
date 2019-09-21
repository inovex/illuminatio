#!/usr/bin/env bash
# abort if any of the following commands fails or variables are undefined
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
    --container-runtime=containerd \
    --cri-socket=/run/containerd/containerd.sock \
    --extra-config=kubelet.container-runtime=remote \
    --extra-config=kubelet.container-runtime-endpoint=unix:///run/containerd/containerd.sock \
    --extra-config=kubelet.image-service-endpoint=unix:///run/containerd/containerd.sock \
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
