#!/bin/bash
#first source your virtualenv

#abort if any of the following commands fails or variables are undefined
set -eu

#install illuminatio
pip3 install -r requirements.txt
python3 setup.py install

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
kubectl apply -f https://docs.projectcalico.org/v3.5/getting-started/kubernetes/installation/hosted/kubernetes-datastore/calico-networking/1.7/calico.yaml
kubectl apply -f local_dev/docker-registry.yml

#use local docker daemon to build
unset DOCKER_TLS_VERIFY
unset DOCKER_HOST
unset DOCKER_CERT_PATH
unset DOCKER_API_VERSION
docker build -t "localhost:5000/illuminatio-runner:dev" -f illuminatio-runner.dockerfile .
mkdir -p /tmp/images

#export the new image
docker save localhost:5000/illuminatio-runner:dev -o /tmp/images/illuminatio

#use minikube docker daemon to push to the insecure registry
eval "$(minikube docker-env)"
if docker images localhost:5000/illuminatio-runner:dev |\
grep localhost:5000/illuminatio-runner:dev
then
  docker rmi localhost:5000/illuminatio-runner:dev
fi
docker load -i /tmp/images/illuminatio
until docker push "localhost:5000/illuminatio-runner:dev"
do
  sleep 1
done
#create a testing service with a suitable policy
kubectl create deployment web --image=nginx
kubectl expose deployment web --port 80 --target-port 80
cat <<EOF | kubectl apply -f -
kind: NetworkPolicy
apiVersion: networking.k8s.io/v1
metadata:
  name: web-deny-all
spec:
  podSelector:
    matchLabels:
      app: web
  ingress: []
EOF

#run illuminatio
illuminatio run --runner-image='localhost:5000/illuminatio-runner:dev'
