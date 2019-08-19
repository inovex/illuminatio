import subprocess
import pytest
from kubernetes import client, config, utils


@pytest.mark.e2e
def test_deny_all_traffic_to_an_application():
    namespace = "01-deny-all"
    config.load_kube_config()
    k8s_client = client.ApiClient()
    corev1 = client.CoreV1Api()

    corev1.create_namespace(client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=namespace,
            labels={"illuminatio-e2e": namespace})))
    utils.create_from_yaml(k8s_client,
                           "e2e-manifests/01-deny-all-traffic-to-an-application.yml",
                           namespace=namespace)

    # ToDo add sleep or wait until all resources are up otherwise we have a race condition
    # ToDo handle execptions
    res = subprocess.run(["illuminatio", "run", "--runner-image=localhost:5000/illuminatio-runner:dev"],
                         capture_output=True,
                         timeout=60)

    assert res.returncode == 0
    # ToDo evaluate result
    print(res.stdout)

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    corev1.delete_namespace(name=namespace)
