# Developing illuminatio

## Prerequisites

- Python 3
- [virtualenv](https://docs.python-guide.org/dev/virtualenvs/#lower-level-virtualenv)
- [minikube](https://github.com/kubernetes/minikube) (tested with version: v0.34.1)

## Setting up the development environment

```bash
virtualenv -p python3.7 .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

Now you can install the illuminatio client:

```bash
python3 setup.py install
```

## Debugging using PyCharm

- Add `input("press Enter to continue")` to the `run()` method to block the process
- Build and start the illuminatio cli in a shell
- You are now able to attach the Python debugger to the process `Run -> Attach to Process...`
- Let the client continue and use your breakpoints etc. within PyCharm

## Local development

We will bootstrap a [Minikube VM](https://kubernetes.io/docs/setup/minikube/) for local development.

### Docker

```bash
# See also: https://github.com/projectcalico/calico/issues/1013
minikube start \
    --network-plugin=cni \
    --extra-config=kubelet.network-plugin=cni \
    --extra-config=kubelet.pod-cidr=192.168.0.0/16 \
    --extra-config=controller-manager.allocate-node-cidrs=true \
    --extra-config=controller-manager.cluster-cidr=192.168.0.0/16 \
    --bootstrapper=kubeadm \
    --host-only-cidr=172.17.17.1/24 \
    --insecure-registry=localhost:5000

# Adding a local Docker Registry
minikube addons enable registry
```

There is also a simple bash script that makes it easier to setup the development env: [start_docker.sh](../local_dev/start_docker.sh)

### Containerd

See also [alternative runtimes](https://github.com/kubernetes/minikube/blob/master/docs/alternative_runtimes.md)

```bash
# See also: https://github.com/projectcalico/calico/issues/1013
minikube start \
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
    --insecure-registry=localhost:5000

# Adding a local Docker Registry
minikube addons enable registry
```

If you want to interact with `containerd` you can use `minikube ssh` to ssh into the minikube VM and run `sudo crictl -r unix:///run/containerd/containerd.sock pods` (or other `crictl` commands).

There is also a simple bash script that makes it easier to setup the development env: [start_containerd.sh](../local_dev/start_containerd.sh)

## Networking

Installing Calico (or other [CNI network plugins](https://kubernetes.io/docs/concepts/cluster-administration/networking/#how-to-implement-the-kubernetes-networking-model)) for example:

```bash
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml
```

## Use the local Docker daemon

In order to test newly build runner images we need to use the [Minikube Docker daemon](https://github.com/kubernetes/minikube/blob/master/docs/reusing_the_docker_daemon.md):

```bash
eval $(minikube docker-env)
```

And also deploy a local docker registry:

```bash
kubectl apply -f local_dev/docker-registry.yml
```

Now you need to add the minikube ip (you can get it with `minikube ip`) to the insecure registries of the [Docker client](https://docs.docker.com/registry/insecure/).
This step is required because we didn't setup any TLS certificate for our testing registry.

**This step is only required for containerd**
We need to configure `containerd` to be able to pull images from our local registry:

```bash
minikube ssh
```

The following commands are executed inside the minikube vm

```bash
# Add the following lines -> see https://github.com/kubernetes/minikube/issues/3444
sudo sed -i '56i\          endpoint = ["http://localhost:5000"]' /etc/containerd/config.toml
sudo sed -i '56i\       [plugins.cri.registry.mirrors."localhost"]' /etc/containerd/config.toml
# Finally restart the containerd service
sudo systemctl restart containerd
# Check everything is working
sudo systemctl status containerd
```

Now we can build locally the new runner image:

```bash
docker build -t "$(minikube ip):5000/illuminatio-runner:dev" .
```

And if you run the following command you should see the new image `docker images`.
In order to be able to pull the image from the local registry we need to push the image there:

```bash
docker push "$(minikube ip):5000/illuminatio-runner:dev"
```

If you change code on the orchestrator run:

```bash
python3 setup.py install
```

## Manual testing

```bash
DOCKER_REGISTRY=$(minikube ip) ./local_dev/run_e2e_tests.sh
```

## Unit Tests

In order to run the unit tests:

```bash
python setup.py test --addopts="-m 'not e2e' --runslow"
```

## Cleanup

If you are done testing (or want to use another container runtime) just delete the current minikube cluster:

```bash
minikube delete
```
