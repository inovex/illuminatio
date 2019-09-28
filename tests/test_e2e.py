import pytest
import subprocess
import tempfile
import yaml
from kubernetes import client, config, utils
from tests.utils import wait_for_deployments_ready

E2E_INPUT_MANIFEST = "e2e-manifests/{e2e_test_case}.yml"
E2E_EXPECTED_YAML = "e2e-manifests/expected/{e2e_test_case}.yml"
E2E_RUNNER_IMAGE = "localhost:5000/illuminatio-runner:dev"


@pytest.fixture
def kubernetes_utils():
    config.load_kube_config()
    k8s_client = client.ApiClient()
    return k8s_client, client.CoreV1Api()


@pytest.fixture(autouse=True)
def clean_cluster(kubernetes_utils):
    k8s_client, core_v1 = *kubernetes_utils
    # delete e2e namespaces created in test setup
    e2e_namespaces = core_v1.list_namespace(label_selector="illuminatio-e2e")
    for namespace in e2e_namespaces.items:
        core_v1.delete_namespace(name=namespace.name)
    # delete illuminatio resources
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0


@pytest.mark.parametrize(
    "e2e_test_case",
    [
        "01-deny-all-traffic-to-an-application"
    ],
)
@pytest.mark.e2e
def test__e2e__clean_setup__results_are_expected(e2e_test_case, kubernetes_utils):
    # unpack kubernetes client
    k8s_client, core_v1 = *kubernetes_utils
    # get input and expected from test case name
    input_manifest = E2E_INPUT_MANIFEST.format(e2e_test_case)
    expected_yaml = E2E_EXPECTED_YAML.format(e2e_test_case)
    # create resources to test with
    utils.create_from_yaml(k8s_client,
                           input_manifest)
    # wait for test resources to be ready
    wait_for_deployments_ready(namespace=e2e_test_case, api=k8s_client.AppsV1Api())
    # run illuminatio, with yaml output for later comparison
    result_file = tempfile.TemporaryFile(suffix=".yaml")
    cmd = ["illuminatio", "run", f"--runner-image={E2E_RUNNER_IMAGE}", f"-o={result_file}"]
    res = subprocess.run(cmd, capture_output=True, timeout=120)
    # assert that command didn't fail
    assert res.returncode == 0
    # load contents of result and expected
    result = yaml.safe_load(result_file)
    expected = yaml.safe_load(expected_yaml)
    # assert that the correct cases have been generated and results match
    assert "cases" in result
    assert expected == result["cases"]
