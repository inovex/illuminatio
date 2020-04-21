import logging
from typing import List
from unittest.mock import MagicMock
import yaml
import pytest

import kubernetes as k8s
from illuminatio.test_orchestrator import NetworkTestOrchestrator


def createOrchestrator(cases):
    orch = NetworkTestOrchestrator(cases, logging.getLogger("orchestrator_test"))
    return orch


def get_manifest(yaml_file):
    asset_path = "tests/assets"
    daemonset_manifest = None

    with open(f"{asset_path}/{yaml_file}", "r") as stream:
        try:
            daemonset_manifest = yaml.safe_load(stream.read())
        except yaml.YAMLError as exc:
            print(exc)

    return daemonset_manifest


def test_refreshClusterResourcess_emptyListApiObjectsReturned_extractsEmptyList():
    # setup an api mock that returns an empty pod list
    api_mock = k8s.client.CoreV1Api()
    empty_pod_list = k8s.client.V1PodList(items=[])
    api_mock.list_pod_for_all_namespaces = MagicMock(return_value=empty_pod_list)
    api_mock.list_service_for_all_namespaces = MagicMock(
        return_value=k8s.client.V1ServiceList(items=[])
    )
    api_mock.list_namespace = MagicMock(
        return_value=k8s.client.V1NamespaceList(items=[])
    )
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
    api_mock.list_service_for_all_namespaces = MagicMock(
        return_value=k8s.client.V1ServiceList(items=[])
    )
    illuminatio_ns = k8s.client.V1Namespace(
        metadata=k8s.client.V1ObjectMeta(name="illuminatio")
    )
    api_mock.list_namespace = MagicMock(
        return_value=k8s.client.V1NamespaceList(items=[illuminatio_ns])
    )

    orch.refresh_cluster_resources(api_mock)
    assert orch.namespace_exists("illuminatio", None)


def test_ensure_project_namespace_exists_not_in_cache():
    orch = createOrchestrator([])
    api_mock = k8s.client.CoreV1Api()
    empty_pod_list = k8s.client.V1PodList(items=[])
    api_mock.list_pod_for_all_namespaces = MagicMock(return_value=empty_pod_list)
    api_mock.list_service_for_all_namespaces = MagicMock(
        return_value=k8s.client.V1ServiceList(items=[])
    )
    api_mock.list_namespace = MagicMock(
        return_value=k8s.client.V1NamespaceList(items=[])
    )

    orch.refresh_cluster_resources(api_mock)

    # Ensure that the cache is empty
    assert orch.current_namespaces is not None
    assert not orch.current_namespaces
    ns = k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name="illuminatio"))
    api_mock.read_namespace = MagicMock(return_value=ns)
    assert orch.namespace_exists("illuminatio", api_mock)
    assert len(orch._current_pods) == 0


def test_create_daemonset_manifest_docker():
    orch = createOrchestrator([])
    orch.set_runner_image("inovex/illuminatio-runner:dev")
    daemon_set_name = "illuminatio-runner"
    service_account_name = "illuminatio-runner"
    config_map_name = "illuminatio-cases-cfgmap"
    container_runtime = "docker://18.9.3"

    expected = get_manifest("docker.yaml")
    result = orch.create_daemonset_manifest(
        daemon_set_name, service_account_name, config_map_name, container_runtime, None
    )
    assert result == expected


def test_create_daemonset_manifest_containerd():
    orch = createOrchestrator([])
    orch.set_runner_image("inovex/illuminatio-runner:dev")
    daemon_set_name = "illuminatio-runner"
    service_account_name = "illuminatio-runner"
    config_map_name = "illuminatio-cases-cfgmap"
    container_runtime = "containerd://1.2.6"

    expected = get_manifest("containerd.yaml")
    result = orch.create_daemonset_manifest(
        daemon_set_name, service_account_name, config_map_name, container_runtime, None
    )
    assert result == expected


def test_create_daemonset_manifest_containerd_custom_socket():
    orch = createOrchestrator([])
    orch.set_runner_image("inovex/illuminatio-runner:dev")
    daemon_set_name = "illuminatio-runner"
    service_account_name = "illuminatio-runner"
    config_map_name = "illuminatio-cases-cfgmap"
    container_runtime = "containerd://1.2.6"
    cri_socket = "/var/run/containerd/containerd.sock"

    expected = get_manifest("containerd_custom_socket.yaml")
    result = orch.create_daemonset_manifest(
        daemon_set_name,
        service_account_name,
        config_map_name,
        container_runtime,
        cri_socket,
    )
    assert result == expected


def test_create_daemonset_manifest_unsupported():
    orch = createOrchestrator([])
    orch.set_runner_image("inovex/illuminatio-runner:dev")
    daemon_set_name = "illuminatio-runner"
    service_account_name = "illuminatio-runner"
    config_map_name = "illuminatio-cases-cfgmap"
    container_runtime = "banana://1337"

    with pytest.raises(NotImplementedError):
        orch.create_daemonset_manifest(
            daemon_set_name,
            service_account_name,
            config_map_name,
            container_runtime,
            None,
        )
