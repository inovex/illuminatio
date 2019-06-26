import kubernetes as k8s
from illuminatio.host import ClusterHost, ExternalHost, LocalHost
from illuminatio.test_case import NetworkTestCase, merge_in_dict, to_yaml, from_yaml

test_host1 = ClusterHost("default", {"app": "test"})
test_host2 = ClusterHost("default", {"app": "test", "label2": "value"})


def test_portString_shouldConnectTrue_outputsPortOnly():
    port = 80
    test_case = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    assert test_case.port_string == str(port)


def test_portString_shouldConnectFalse_outputsPortWithMinusPrefix():
    port = 80
    test_case = NetworkTestCase(LocalHost(), LocalHost(), port, False)
    assert test_case.port_string == "-" + str(port)


# Below equality tests

def test_NetworkTestCase_eq_differentFromHost_returnsFalse():
    port = 80
    case1 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    case2 = NetworkTestCase(test_host1, LocalHost(), port, True)
    assert case1 != case2


def test_NetworkTestCase_eq_differentToHost_returnsFalse():
    port = 80
    case1 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    case2 = NetworkTestCase(LocalHost(), test_host1, port, True)
    assert case1 != case2


def test_NetworkTestCase_eq_differentPort_returnsFalse():
    port = 80
    case1 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    case2 = NetworkTestCase(LocalHost(), LocalHost(), port + 1, True)
    assert case1 != case2


def test_NetworkTestCase_eq_differentShouldConnect_returnsFalse():
    port = 80
    case1 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    case2 = NetworkTestCase(LocalHost(), LocalHost(), port, False)
    assert case1 != case2


def test_NetworkTestCase_eq_sameFieldsLocalHostsOnly_returnsTrue():
    port = 80
    case1 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    case2 = NetworkTestCase(LocalHost(), LocalHost(), port, True)
    assert case1 == case2


def test_NetworkTestCase_eq_sameFieldsVariousHosts_returnsTrue():
    port = 80
    test_host1 = ClusterHost("a", {"a": "b"})
    test_host1_copy = ClusterHost("a", {"a": "b"})
    test_host2 = ExternalHost("192.168.0.1")
    test_host2_copy = ExternalHost("192.168.0.1")
    case1 = NetworkTestCase(test_host1, test_host2, port, True)
    case2 = NetworkTestCase(test_host1_copy, test_host2_copy, port, True)
    assert case1 == case2


def test_NetworkTestCase_in_sameFieldsVariousHosts_returnsTrue():
    port = 80
    test_host1 = ClusterHost("a", {"a": "b"})
    test_host1_copy = ClusterHost("a", {"a": "b"})
    test_host2 = ExternalHost("192.168.0.1")
    test_host2_copy = ExternalHost("192.168.0.1")
    case_list = [NetworkTestCase(test_host1, test_host2, port, True)]
    copy_case = NetworkTestCase(test_host1_copy, test_host2_copy, port, True)
    assert copy_case in case_list


# Below: ClusterHost.matches tests

def test_ClusterHost_matches_podGivenAndFromHostIsClusterHostsWithDifferentNamespaceSameLabels_returnsFalse():
    meta = k8s.client.V1ObjectMeta(namespace="other-ns", labels=test_host1.pod_labels)
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert test_host1.matches(non_matching_pod) is False


def test_ClusterHost_matches_podGivenAndFromHostIsClusterHostsWithSametNamespaceDifferentLabels_returnsFalse():
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels={"app": "wrong"})
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert test_host1.matches(non_matching_pod) is False


def test_ClusterHost_matches_podGivenAndFromHostIsClusterHostsWithSametNamespaceSameLabels_returnsTrue():
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels=test_host1.pod_labels)
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert test_host1.matches(non_matching_pod) is True


def test_ClusterHost_matches_podGivenAndFromHostIsClusterHostsWithSupersetLabelsOfPod_returnsFalse():
    test_host = ClusterHost("default", {"app": "web", "load": "high"})
    meta = k8s.client.V1ObjectMeta(namespace=test_host.namespace, labels={"app": test_host.pod_labels["app"]})
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert test_host.matches(non_matching_pod) is False


def test_ClusterHost_matches_podGivenAndFromHostIsClusterHostsWithSubsetLabelsOfPod_returnsTrue():
    meta = k8s.client.V1ObjectMeta(namespace="default", labels={"app": "web", "load": "high"})
    test_host = ClusterHost(meta.namespace, {"app": meta.labels["app"]})
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert test_host.matches(non_matching_pod) is True


def test_TestCase_matches_podGivenAndHostsAreNotClusterHosts_returnsFalse():
    case = NetworkTestCase(LocalHost(), LocalHost(), 80, False)
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels=test_host1.pod_labels)
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert case.matches([non_matching_pod]) is False


def test_TestCase_matches_podGivenAndOnlyFromHostMatches_returnsFalse():
    case = NetworkTestCase(test_host1, LocalHost(), 80, False)
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels=test_host1.pod_labels)
    from_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert case.matches([from_matching_pod]) is False


def test_TestCase_matches_podGivenAndOnlyToHostMatches_returnsFalse():
    case = NetworkTestCase(LocalHost(), test_host1, 80, False)
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels=test_host1.pod_labels)
    to_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert case.matches([to_matching_pod]) is False


def test_TestCase_matches_podGivenAndBothHoststMatch_returnsTrue():
    case = NetworkTestCase(test_host2, test_host1, 80, False)
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace, labels=test_host2.pod_labels)
    matching_pod = k8s.client.V1Pod(metadata=meta)
    assert case.matches([matching_pod]) is True


def test_TestCase_matches_podGivenLabelsNone_returnsFalse():
    case = NetworkTestCase(test_host2, test_host1, 80, False)
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace)
    non_matching_pod = k8s.client.V1Pod(metadata=meta)
    assert case.matches([non_matching_pod]) is False


def test_ClusterHost_matches_svcGivenAndFromHostIsClusterHostsWithSametNamespaceSameLabels_returnsTrue():
    # only one positive and negative test, as the same label matching was used as above
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace)
    matching_svc = k8s.client.V1Service(metadata=meta)
    matching_svc.spec = k8s.client.V1ServiceSpec()
    matching_svc.spec.selector = {k: v for k, v in test_host1.pod_labels.items()}
    assert test_host1.matches(matching_svc) is True


def test_ClusterHOst_matches_svcGivenSpecSelectorNone_returnsFalse():
    meta = k8s.client.V1ObjectMeta(namespace=test_host1.namespace)
    matching_svc = k8s.client.V1Service(metadata=meta)
    matching_svc.spec = k8s.client.V1ServiceSpec()
    assert test_host1.matches(matching_svc) is False


# Below: mergeInDict

def test_mergeInDict_emptyList_returnsEmptyDict():
    assert merge_in_dict([]) == {}


def test_mergeInDict_oneCase_returnsDict():
    case = NetworkTestCase(test_host1, test_host2, 80, False)
    expected = {test_host1.to_identifier(): {test_host2.to_identifier(): ["-80"]}}
    assert merge_in_dict([case]) == expected


def test_mergeInDict_twoCasesNoConflicts_returnsDict():
    case1 = NetworkTestCase(test_host1, test_host2, 80, False)
    case2 = NetworkTestCase(test_host2, test_host1, 80, False)
    expected = {test_host1.to_identifier(): {test_host2.to_identifier(): ["-80"]},
                test_host2.to_identifier(): {test_host1.to_identifier(): ["-80"]}}
    assert merge_in_dict([case1, case2]) == expected


def test_mergeInDict_twoCasesSameFromHostDifferentToHost_returnsDict():
    case1 = NetworkTestCase(test_host1, test_host2, 80, False)
    case2 = NetworkTestCase(test_host1, test_host1, 80, False)
    expected = {test_host1.to_identifier(): {test_host2.to_identifier(): ["-80"],
                                             test_host1.to_identifier(): ["-80"]}}
    assert merge_in_dict([case1, case2]) == expected


def test_mergeInDict_twoCasesSameFromHostSameToHost_returnsDict():
    case1 = NetworkTestCase(test_host1, test_host2, 80, False)
    case2 = NetworkTestCase(test_host1, test_host2, 8080, True)
    expected = {test_host1.to_identifier(): {test_host2.to_identifier(): ["-80", "8080"]}}
    assert merge_in_dict([case1, case2]) == expected


# Below: yaml conversion tests


def test_toYaml_oneTestCase_returnsExpectedYaml():
    testHost = ClusterHost("namespc", {"label": "val"})
    case = NetworkTestCase(LocalHost(), testHost, 80, False)
    expected = "localhost:\n  namespc:label=val: ['-80']\n"
    assert to_yaml([case]) == expected


def test_fromYaml_simpleSampleYaml_returnsExpectedCase():
    testYaml = "localhost:\n  namespc:label=val: ['-80']\n"
    expectedHost = ClusterHost("namespc", {"label": "val"})
    expected = NetworkTestCase(LocalHost(), expectedHost, 80, False)
    actual = from_yaml(testYaml)
    assert len(actual) == 1
    assert actual[0] == expected
