import logging
from typing import List
from unittest.mock import MagicMock

import kubernetes as k8s
from illuminatio.test_orchestrator import NetworkTestOrchestrator


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
    assert orch._current_pods is not None
    assert not orch._current_pods


def test_ensure_project_namespace_exists_in_cache():
    orch = createOrchestrator([])
    api_mock = k8s.client.CoreV1Api()
    empty_pod_list = k8s.client.V1PodList(items=[])
    api_mock.list_pod_for_all_namespaces = MagicMock(return_value=empty_pod_list)
    api_mock.list_service_for_all_namespaces = MagicMock(return_value=k8s.client.V1ServiceList(items=[]))
    illuminatio_ns = k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="illuminatio"))
    api_mock.list_namespace = MagicMock(return_value=k8s.client.V1NamespaceList(items=[illuminatio_ns]))

    orch.refresh_cluster_resources(api_mock)
    assert orch.namespace_exists("illuminatio", None)


def test_ensure_project_namespace_exists_not_in_cache():
    orch = createOrchestrator([])
    api_mock = k8s.client.CoreV1Api()
    empty_pod_list = k8s.client.V1PodList(items=[])
    api_mock.list_pod_for_all_namespaces = MagicMock(return_value=empty_pod_list)
    api_mock.list_service_for_all_namespaces = MagicMock(return_value=k8s.client.V1ServiceList(items=[]))
    api_mock.list_namespace = MagicMock(return_value=k8s.client.V1NamespaceList(items=[]))

    orch.refresh_cluster_resources(api_mock)

    # Ensure that the cache is empty
    assert orch.current_namespaces is not None
    assert not orch.current_namespaces
    ns = k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="illuminatio"))
    api_mock.read_namespace = MagicMock(return_value=ns)
    assert orch.namespace_exists("illuminatio", api_mock)
