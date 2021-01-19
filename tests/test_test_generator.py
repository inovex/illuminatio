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
            id="Allow all traffic in namespace",
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
            id="Deny all traffic in namespace",
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
            id="Allow labelled Pods to communicate with all Pods in the same Namespace",
        ),
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="allow-all-to-labelled-pods", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(
                            match_labels={"test.io/test-123_XYZ": "test_456-123.ABC"}
                        ),
                        ingress=[k8s.client.V1NetworkPolicyIngressRule(_from=None)],
                    ),
                )
            ],
            [
                NetworkTestCase(
                    GenericClusterHost({}, {}),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"},
                    ),
                    "*",
                    True,
                )
            ],
            id="Allow all Pods to communicate to labelled Pods in the same Namespace",
        ),
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="allow-labelled-pods", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(
                            match_labels={"test.io/test-123_XYZ": "test_456-123.ABC"}
                        ),
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
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"}
                    ),
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
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"}
                    ),
                    "*",
                    False,
                ),
                NetworkTestCase(
                    ClusterHost(
                        INVERTED_ATTRIBUTE_PREFIX + "default",
                        {"test.io/test-123_XYZ": "test_456-123.ABC"},
                    ),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"}
                    ),
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
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.ABC"}
                    ),
                    "*",
                    False,
                ),
            ],
            id="Allow labelled Pods to communicate to Pods with the same labels in the same Namespace",
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
                                ],
                                ports=[
                                    k8s.client.V1NetworkPolicyPort(
                                        port=None, protocol="TCP"
                                    )
                                ],
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
            id="Correctly handle portless NetworkPolicy",
        ),
        pytest.param(
            [k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="default"))],
            [
                k8s.client.V1NetworkPolicy(
                    metadata=k8s.client.V1ObjectMeta(
                        name="allow-named-port", namespace="default"
                    ),
                    spec=k8s.client.V1NetworkPolicySpec(
                        pod_selector=k8s.client.V1LabelSelector(
                            match_labels={
                                "test.io/test-123_XYZ": "test_456-123.RECEIVER"
                            }
                        ),
                        ingress=[
                            k8s.client.V1NetworkPolicyIngressRule(
                                _from=[
                                    k8s.client.V1NetworkPolicyPeer(
                                        pod_selector=k8s.client.V1LabelSelector(
                                            match_labels={
                                                "test.io/test-123_XYZ": "test_456-123.SENDER"
                                            }
                                        )
                                    )
                                ],
                                ports=[
                                    k8s.client.V1NetworkPolicyPort(
                                        port="mynamedport", protocol="TCP"
                                    )
                                ],
                            )
                        ],
                    ),
                )
            ],
            [
                NetworkTestCase(
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.SENDER"}
                    ),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.RECEIVER"}
                    ),
                    "mynamedport",
                    True,
                ),
                NetworkTestCase(
                    ClusterHost(
                        INVERTED_ATTRIBUTE_PREFIX + "default",
                        {"test.io/test-123_XYZ": "test_456-123.SENDER"},
                    ),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.RECEIVER"}
                    ),
                    "mynamedport",
                    False,
                ),
                NetworkTestCase(
                    ClusterHost(
                        "default",
                        {
                            INVERTED_ATTRIBUTE_PREFIX
                            + "test.io/test-123_XYZ": "test_456-123.SENDER"
                        },
                    ),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.RECEIVER"}
                    ),
                    "mynamedport",
                    False,
                ),
                NetworkTestCase(
                    ClusterHost(
                        INVERTED_ATTRIBUTE_PREFIX + "default",
                        {
                            INVERTED_ATTRIBUTE_PREFIX
                            + "test.io/test-123_XYZ": "test_456-123.SENDER"
                        },
                    ),
                    ClusterHost(
                        "default", {"test.io/test-123_XYZ": "test_456-123.RECEIVER"}
                    ),
                    "mynamedport",
                    False,
                ),
            ],
            id="Correctly handle NetworkPolicy with named Port",
        ),
    ],
)
def test__generate_test_cases(namespaces, networkpolicies, expected_testcases):
    cases, _ = gen.generate_test_cases(networkpolicies, namespaces)
    assert sorted(cases) == sorted(expected_testcases)
