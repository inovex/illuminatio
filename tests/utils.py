import pytest
import time
import kubernetes as k8s

def wait_for_deployments_ready(namespace,
                               api: k8s.client.AppsV1Api,
                               max_tries=30,
                               sleep_time=5):
    """
    Checks namespace for Deployments and waits until all are fully ready
    """
    tries = 0
    print(f"Ensure that Pods of Deployments in {namespace} are ready")
    while tries <= max_tries:
        try:
            deployments = api.list_namespaced_deployment(namespace=namespace)
            if all([_deployment_ready(d) for d in deployments.items]):
                return
        except k8s.client.rest.ApiException as api_exception:
            print(api_exception)
        time.sleep(sleep_time)
        tries += 1
    waited_time = tries * sleep_time
    pytest.fail(f"Deployments in {namespace} have not come up in {waited_time}s")


def _deployment_ready(deployment):
    ready = deployment.status.number_ready
    scheduled = deployment.status.desired_number_scheduled
    return scheduled > 0 and scheduled == ready
