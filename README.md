# Illuminatio - The kubernetes network policy validator

Illuminatio is a tool for automatically testing kubernetes network policies.
Simply execute `illuminatio clean run`
and Illuminatio will scan your kubernetes cluster for network policies, build test cases accordingly and execute them
to determine if the policies are in effect.

An overview of the concept is visualized in [the concept doc](docs/concept.md).

# Getting started
Follow these instructions to get Illuminatio up and running.

## Prerequisites

- Python 3
- Pip 3

## Installation

with pip:

```bash
pip3 install illuminatio
```

or directly from the repository:

```bash
git clone https://github.com/inovex/illuminatio
cd illuminatio
python3 setup.py install
cd ..
```

## Example Usage

Create a Deployment to test with:

```bash
kubectl create deployment web --image=nginx
kubectl expose deployment web --port 80 --target-port 80
```

Define and create a NetworkPolicy for your Deployment:

```bash
cat <<EOF | kubectl create -f -
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
```

Test your newly created NetworkPolicy:

```bash
$ illuminatio clean run
```
```
Starting cleaning resources with policies ['on-request', 'always']
Deleting namespacess [] with cleanup policy on-request
Deleting namespacess [] with cleanup policy always
Deleting DSs in default with cleanup policy on-request
Deleting pods in default with cleanup policy on-request
Deleting svcs in default with cleanup policy on-request
Deleting CfgMaps in default with cleanup policy on-request
Deleting CRBs  with cleanup policy on-request globally
Deleting SAs in default with cleanup policy on-request
Deleting DSs in default with cleanup policy always
Deleting pods in default with cleanup policy always
Deleting svcs in default with cleanup policy always
Deleting CfgMaps in default with cleanup policy always
Deleting CRBs  with cleanup policy always globally
Deleting SAs in default with cleanup policy always
Finished cleanUp

Starting test generation and run.
Got cases: [NetworkTestCase(from=ClusterHost(namespace=default, podLabels={'app': 'web'}), to=ClusterHost(namespace=default, podLabels={'app': 'web'}), port=-*)]
Generated 1 cases in 0.0701 seconds
FROM             TO               PORT
default:app=web  default:app=web  -*  

Using existing cluster role
Creating cluster role binding
TestResults: {'default:app=web': {'default:app=web': {'-*': {'success': True}}}}
Finished running 1 tests in 18.7413 seconds
FROM             TO               PORT  RESULT
default:app=web  default:app=web  -*    success
```

The `clean` keyword assures that illuminatio clears all potentially existing resources created in past illuminatio runs to prevent potential issues, however no user generated resources are affected.

*PLEASE NOTE* that currently each new run requires a clean, as the runners do not continuously look for new cases.

For the case that you really want to keep the generated resources you are free to omit the `clean` keyword.

If you are done testing you might want to easily delete all resources created by illuminatio:

```bash
illuminatio clean
```

To preview generated test cases without running tests use `illuminatio run`'s `--dry` option:

```bash
illuminatio run --dry
```
```
Starting test generation and run.
Got cases: [NetworkTestCase(from=ClusterHost(namespace=default, podLabels={'app': 'web'}), to=ClusterHost(namespace=default, podLabels={'app': 'web'}), port=-*)]
Generated 1 cases in 0.0902 seconds
FROM             TO               PORT
default:app=web  default:app=web  -*  

Skipping test execution as --dry was set
```

All options and further information can be found using the `--help` flag on any level:

```bash
illuminatio --help
```
```
Usage: illuminatio [OPTIONS] COMMAND1 [ARGS]... [COMMAND2 [ARGS]...]...

Options:
  -v, --verbosity LVL  Either CRITICAL, ERROR, WARNING, INFO or DEBUG
  --incluster
  --help               Show this message and exit.

Commands:
  clean
  run
```

## References
Example Network Policies are inspired by:
https://github.com/ahmetb/kubernetes-network-policy-recipes

## Contributing
We are happy to read your [issues](https://github.com/inovex/illuminatio/issues) and accept your [Pull Requests.](https://github.com/inovex/illuminatio/compare)

For more information on developing illuminatio refer to [the development docs](docs/developing.md).
