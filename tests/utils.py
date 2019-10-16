import pytest
import time
import kubernetes as k8s


def wait_for_deployments_ready(e2_test_case,
                               api: k8s.client.AppsV1Api,
                               core_api: k8s.client.CoreV1Api,
                               max_tries=30,
                               sleep_time=5):
    """
    Checks e2_test_case's namespaces for Deployments and waits until all are fully ready
    """
    label_selector = f"illuminatio-e2e={e2_test_case}"
    print(f"Getting e2e namespaces with label_selector {label_selector}")
    namespace_list = core_api.list_namespace(label_selector=label_selector)
    namespaces = [n.metadata.name for n in namespace_list.items]
    tries = 0
    print(f"Ensure that Pods of Deployments in {namespaces} are ready")
    while tries <= max_tries:
        try:
            deployments = []
            for ns in namespaces:
                deployments += api.list_namespaced_deployment(namespace=ns)
            if all([_deployment_ready(d) for d in deployments.items]):
                return
        except k8s.client.rest.ApiException as api_exception:
            print(api_exception)
        time.sleep(sleep_time)
        tries += 1
    waited_time = tries * sleep_time
    pytest.fail(f"Deployments in {namespaces} have not come up in {waited_time}s")


def _deployment_ready(deployment):
    ready = deployment.status.number_ready
    scheduled = deployment.status.desired_number_scheduled
    return scheduled > 0 and scheduled == ready
