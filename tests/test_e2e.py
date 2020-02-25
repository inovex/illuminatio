import pytest
import subprocess
import tempfile
import yaml
from kubernetes import client, config, utils
from tests.utils import wait_for_deployments_ready

E2E_INPUT_MANIFEST = "e2e-manifests/{}.yml"
E2E_EXPECTED_YAML = "e2e-manifests/expected/{}.yml"
E2E_RUNNER_IMAGE = "localhost:5000/illuminatio-runner:dev"


@pytest.fixture
def load_kube_config():
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
                         timeout=120)

    assert res.returncode == 0
    # ToDo evaluate result
    print(res.stdout)

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    corev1.delete_namespace(name=namespace)
