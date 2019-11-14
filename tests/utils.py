import pytest
import time
import kubernetes as k8s


def wait_for_deployments_ready(e2_test_case,
                               api: k8s.client.AppsV1Api,
                               max_tries=30,
                               sleep_time=5):
    """
    Checks e2_test_case's namespaces for Deployments and waits until all are fully ready
    """
    label_selector = f"illuminatio-e2e={e2_test_case}"
    tries = 0
    print(f"Ensure that Pods of Deployments with labels {label_selector} are ready")
    while tries <= max_tries:
        try:
            deployments = api.list_deployment_for_all_namespaces(label_selector=label_selector)
            if all([_deployment_ready(d) for d in deployments.items]):
                return
        except k8s.client.rest.ApiException as api_exception:
            print(api_exception)
        time.sleep(sleep_time)
        tries += 1
    waited_time = tries * sleep_time
    pytest.fail(f"Deployments in {label_selector} have not come up in {waited_time}s")


def _deployment_ready(deployment):
    ready = deployment.status.ready_replicas or 0
    scheduled = deployment.status.replicas or 0
    return scheduled > 0 and scheduled == ready
