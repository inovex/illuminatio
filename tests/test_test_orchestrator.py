import logging
from typing import List
from unittest.mock import MagicMock

import kubernetes as k8s
from illuminatio.host import ClusterHost
from illuminatio.test_orchestrator import NetworkTestOrchestrator

testHost1 = ClusterHost("default", {"app": "test"})
testHost2 = ClusterHost("default", {"app": "other"})


def createOrchestrator(cases):
    orch = NetworkTestOrchestrator(cases, logging.getLogger("orchestrator_test"))
    return orch


def test__refreshClusterResourcess_emptyListApiObjectsReturned_extractsEmptyList():
    # setup an api mock that returns an empty pod list
    api_mock = k8s.client.CoreV1Api()
    empty_pod_list = k8s.client.V1PodList(items=[])
    api_mock.list_pod_for_all_namespaces = MagicMock(return_value=empty_pod_list)
    api_mock.list_service_for_all_namespaces = MagicMock(return_value=k8s.client.V1ServiceList(items=[]))
    api_mock.list_namespace = MagicMock(return_value=k8s.client.V1NamespaceList(items=[]))
    # test that this results in an empty list
    orch = createOrchestrator([])
    orch.refresh_cluster_resources(api_mock)
    assert isinstance(orch._current_pods, List)
    assert len(orch._current_pods) == 0
