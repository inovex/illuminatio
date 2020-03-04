# Developing illuminatio

## Prerequisites

- Python 3
- [virtualenv](https://docs.python-guide.org/dev/virtualenvs/#lower-level-virtualenv)
- [minikube](https://github.com/kubernetes/minikube) (tested with version: v0.34.1)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start)
- [Docker Registry](https://hub.docker.com), you can also run your own registry in the cluster (not covered in this document)

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

## Local development

We will bootstrap a [Minikube VM](https://kubernetes.io/docs/setup/minikube/) for local development.

### Docker

There is a simple bash script that makes it easier to setup the development env: [start_docker.sh](../local_dev/start_docker.sh)

### Containerd

There is a simple bash script that makes it easier to setup the development env: [start_containerd.sh](../local_dev/start_containerd.sh)

## Networking

Installing Calico (or other [CNI network plugins](https://kubernetes.io/docs/concepts/cluster-administration/networking/#how-to-implement-the-kubernetes-networking-model)) for example:

```bash
# actually we don't need the rbac rules since minikube has rbac deactivated per default
kubectl apply -f https://docs.projectcalico.org/v3.9/getting-started/kubernetes/installation/hosted/kubernetes-datastore/calico-networking/1.7/calico.yaml
```

## Build images

Prepare these env variables:

```bash
# adjust these for your requirements
export IMAGE_REPO=inovex
export IMAGE_TAG=dev
```

Now we can build the new runner image:

```bash
make image-build
```

In order to be able to pull the image we need to push the image:

```bash
make image-push
```

If you change code on the orchestrator run:

```bash
python3 setup.py install
```

## e2e testing

```bash
E2E_RUNNER_IMAGE="${IMAGE_REPO}/illuminatio-runner:${IMAGE_TAG}" python setup.py test --addopts="-m e2e"
```

## Unit Tests

In order to run the unit tests:

```bash
python3 setup.py test --addopts --runslow
```

## Cleanup

If you are done testing (or want to use another container runtime) just delete the current minikube cluster:

```bash
minikube delete
```
