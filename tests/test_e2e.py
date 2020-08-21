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


@pytest.fixture
def api_client(load_kube_config):
    return client.ApiClient()


@pytest.fixture
def core_v1(load_kube_config):
    return client.CoreV1Api()


@pytest.fixture
def apps_v1(load_kube_config):
    return client.AppsV1Api()


@pytest.fixture(autouse=True)
def clean_cluster(core_v1):
    yield  # below code is executed after test(s)
    # delete e2e namespaces created in test setup
    e2e_namespaces = core_v1.list_namespace(label_selector="illuminatio-e2e")
    for namespace in e2e_namespaces.items:
        core_v1.delete_namespace(name=namespace.metadata.name)
    # delete illuminatio resources
    try:
        print(subprocess.check_output(["illuminatio", "clean"]))
    except subprocess.CalledProcessError as cpe:
        print(cpe)


@pytest.mark.parametrize(
    "e2e_test_case",
    [
        "01-deny-all-traffic-to-an-application",
        "labels-with-all-legal-characters",
        "max-length-labels",
    ],
)
@pytest.mark.e2e
def test__e2e__clean_setup__results_are_expected(e2e_test_case, api_client, apps_v1):
    # get input and expected from test case name
    input_manifest = E2E_INPUT_MANIFEST.format(e2e_test_case)
    expected_yaml = E2E_EXPECTED_YAML.format(e2e_test_case)
    # create resources to test with
    utils.create_from_yaml(api_client, input_manifest)
    # wait for test resources to be ready
    wait_for_deployments_ready(e2e_test_case, api=apps_v1)
    # run illuminatio, with yaml output for later comparison
    tmp_dir = tempfile.TemporaryDirectory()
    result_file_name = f"{tmp_dir.name}/result.yaml"
    with open(result_file_name, "w") as result_file:
        cmd = [
            "illuminatio",
            "run",
            "--runner-image",
            f"{E2E_RUNNER_IMAGE}",
            "-o",
            f"{result_file.name}",
        ]
        try:
            print(subprocess.check_output(cmd, timeout=120))
        except subprocess.CalledProcessError as cpe:
            print(cpe)
    # load contents of result and expected
    result = None
    try:
        with open(result_file_name, "r") as stream:
            result = yaml.safe_load(stream)
    except OSError:
        pass
    assert result is not None, f"Could not load result from {result_file_name}"
    expected = None

    try:
        with open(expected_yaml, "r") as stream:
            expected = yaml.safe_load(stream)
    except OSError:
        pass
    assert expected is not None, f"Could not load expected from {expected_yaml}"
    # assert that the correct cases have been generated and results match
    assert "cases" in result
    try:
        assert expected == result["cases"]
    except AssertionError as e:
        print("Generated cases did not match expected. Generated:\n")
        print(yaml.dump(result["cases"]))
        print("Expected:\n")
        print(yaml.dump(expected))
        raise e
