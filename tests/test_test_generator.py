import logging
import pytest

import kubernetes as k8s

from illuminatio.test_generator import NetworkTestCaseGenerator
from illuminatio.host import GenericClusterHost, ClusterHost
from illuminatio.test_case import NetworkTestCase
from illuminatio.util import INVERTED_ATTRIBUTE_PREFIX

gen = NetworkTestCaseGenerator(logging.getLogger("test_test_generator"))


@pytest.mark.parametrize(
    "namespaces,networkpolicies,expected_testcases",
    [
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="allow-all", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(match_labels=None),
                        ingress=[k8s.client.V1NetworkPolicyIngressRule(_from=None)],
                    ),
                )
            ],
            [
                NetworkTestCase(
                    GenericClusterHost({}, {}), ClusterHost("default", {}), "*", True
                )
            ],
            id="Allow All",
        ),
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="deny-all", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(match_labels=None),
                        ingress=None,
                    ),
                )
            ],
            [
                NetworkTestCase(
                    ClusterHost("default", {}), ClusterHost("default", {}), "*", False
                )
            ],
            id="Deny All",
        ),
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="allow-labelled-pods", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(match_labels={}),
                        ingress=[
                            k8s.client.V1NetworkPolicyIngressRule(
                                _from=[
                                    k8s.client.V1NetworkPolicyPeer(
                                        pod_selector=k8s.client.V1LabelSelector(
                                            match_labels={
                                                "test.io/test-123_XYZ": "test_456-123.ABC"
                                            }
                                        )
                                    )
                                ]
                            )
                        ],
                    ),
                )
            ],
            [
                NetworkTestCase(
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"}
                    ),
                    ClusterHost("default", {}),
                    "*",
                    True,
                ),
                NetworkTestCase(
                    ClusterHost(
                        "default",
                        {
                            INVERTED_ATTRIBUTE_PREFIX
                            + "test.io/test-123_XYZ": "test_456-123.ABC"
                        },
                    ),
                    ClusterHost("default", {}),
                    "*",
                    False,
                ),
                NetworkTestCase(
                    ClusterHost(
                        INVERTED_ATTRIBUTE_PREFIX + "default",
                        {"test.io/test-123_XYZ": "test_456-123.ABC"},
                    ),
                    ClusterHost("default", {}),
                    "*",
                    False,
                ),
                NetworkTestCase(
                    ClusterHost(
                        INVERTED_ATTRIBUTE_PREFIX + "default",
                        {
                            INVERTED_ATTRIBUTE_PREFIX
                            + "test.io/test-123_XYZ": "test_456-123.ABC"
                        },
                    ),
                    ClusterHost("default", {}),
                    "*",
                    False,
                ),
            ],
            id="Allow all pods to labelled pods in namespace",
        ),
    ],
)
def test__generate_test_cases(namespaces, networkpolicies, expected_testcases):
    cases, _ = gen.generate_test_cases(networkpolicies, namespaces)
    assert sorted(cases) == sorted(expected_testcases)
