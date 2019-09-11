import logging

import kubernetes as k8s

from illuminatio.test_generator import NetworkTestCaseGenerator
from illuminatio.host import GenericClusterHost, ClusterHost
from illuminatio.test_case import NetworkTestCase
from illuminatio.util import INVERTED_ATTRIBUTE_PREFIX

gen = NetworkTestCaseGenerator(logging.getLogger("test_test_generator"))


def test__generate_test_cases__allow_all__returns_single_positive_case():
    namespaces = [
        _generate_namespace("default")
        ]
    networkpolicies = [
        _generate_allow_all_network_policy("default")
        ]
    expected = [
        NetworkTestCase(
            GenericClusterHost({}, {}),
            ClusterHost("default", {}),
            "*",
            True
            )
        ]
    cases, _ = gen.generate_test_cases(networkpolicies, namespaces)
    assert len(cases) == 1
    assert cases == expected


def test__generate_test_cases__deny_all__returns_single_negative_case():
    namespaces = [
        _generate_namespace("default")
        ]
    networkpolicies = [
        _generate_deny_all_network_policy("default")
        ]
    expected = [
        NetworkTestCase(
            ClusterHost("default", {}),
            ClusterHost("default", {}),
            "*",
            False
            )
        ]
    cases, _ = gen.generate_test_cases(networkpolicies, namespaces)
    assert len(cases) == 1
    assert cases == expected


def test__generate_test_cases__allow_some_pods__returns_negative_and_positive_case():
    allowed_namespace = "default"
    forbiden_namespace = INVERTED_ATTRIBUTE_PREFIX + allowed_namespace
    allowed_labels = {"test": "test"}
    forbidden_labels = {INVERTED_ATTRIBUTE_PREFIX + "test": "test"}
    namespaces = [
        _generate_namespace(allowed_namespace)
        ]
    networkpolicies = [
        _generate_allow_labelled_pods_network_policy(allowed_namespace, labels=allowed_labels)
        ]
    expected = [
        NetworkTestCase(
            ClusterHost(allowed_namespace, allowed_labels),
            ClusterHost(allowed_namespace, {}),
            "*",
            True
            ),
        NetworkTestCase(
            ClusterHost(allowed_namespace, forbidden_labels),
            ClusterHost(allowed_namespace, {}),
            "*",
            False
            ),
        NetworkTestCase(
            ClusterHost(forbiden_namespace, allowed_labels),
            ClusterHost(allowed_namespace, {}),
            "*",
            False
            ),
        NetworkTestCase(
            ClusterHost(forbiden_namespace, forbidden_labels),
            ClusterHost(allowed_namespace, {}),
            "*",
            False
            )
        ]
    cases, _ = gen.generate_test_cases(networkpolicies, namespaces)
    assert len(cases) == 4
    assert sorted(cases) == sorted(expected)


def _generate_namespace(name, labels=None):
    metadata = k8s.client.V1ObjectMeta(name=name, labels=labels)
    return k8s.client.V1Namespace(metadata=metadata)


def _generate_allow_all_network_policy(namespace):
    policy = __generate_base_policy(name="allow-all", namespace=namespace)
    policy.spec.ingress = [k8s.client.V1NetworkPolicyIngressRule(_from=None)]
    return policy


def _generate_deny_all_network_policy(namespace):
    return __generate_base_policy(name="deny-all", namespace=namespace)


def _generate_allow_labelled_pods_network_policy(namespace, labels=None, port=None):
    policy = __generate_base_policy(name="allow-all", namespace=namespace)
    _from = None
    ports = None
    if labels is not None:
        pod_selector = k8s.client.V1LabelSelector(match_labels=labels)
        _from = [k8s.client.V1NetworkPolicyPeer(pod_selector=pod_selector)]
    if port is not None:
        ports = [k8s.client.V1NetworkPolicyPort(port)]
    policy.spec.ingress = [k8s.client.V1NetworkPolicyIngressRule(_from=_from, ports=ports)]
    return policy


def __generate_base_policy(name, namespace):
    metadata = k8s.client.V1ObjectMeta(name=name, namespace=namespace)
    pod_selector = k8s.client.V1LabelSelector(match_labels=None)
    spec = k8s.client.V1NetworkPolicySpec(pod_selector=pod_selector, ingress=None)
    return k8s.client.V1NetworkPolicy(metadata=metadata, spec=spec)
