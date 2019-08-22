from os import path

import yaml
import pytest
import subprocess
from kubernetes import client, config
from create_from_yaml import create_from_yaml


def validate_illuminatio_was_successful(results_dict):
    if results_dict["cases"] is None:
        raise ValueError("Error: Invalid output, test cases seem to be missing")
    cases_dict = results_dict["cases"]
    for case in cases_dict:
        raw_case = cases_dict[case]
        for namespace in raw_case:
            result = raw_case[namespace]
            for ports in result:
                success = result[ports]["success"]
                if success is not True:
                    raise ValueError("Error: One or more test cases of illuminatio have failed")


@pytest.mark.e2e
def test_deny_all_traffic_to_an_application():
    config.load_kube_config()
    k8s_client = client.ApiClient()
    create_from_yaml(k8s_client,
                     "e2e-manifests/01-deny-all-traffic-to-an-application.yml",
                     verbose=False, wait_until_ready=True)
    results_yaml_file = "result.yml"
    # run illuminatio and store the results to a yaml file
    res = subprocess.run(["illuminatio", "clean", "run", "--runner-image=localhost:5000/illuminatio-runner:dev",
                          "-o", results_yaml_file],
                         capture_output=True,
                         timeout=60)
    assert res.returncode == 0

    # evaluate the results of illuminatio

    with open(path.abspath(results_yaml_file)) as f:
        yaml_document = yaml.safe_load_all(f)
        for results_dict in yaml_document:
            validate_illuminatio_was_successful(results_dict)
            expected_dict = {'cases': {'01-deny-all:app=web': {'01-deny-all:app=web': {'-*': {'success': True}}}},
                             'results': {'mappings': {'ports': {'01-deny-all:app=web': {
                                                                '01-deny-all:app=web': {'-*': '-80'}}},
                                         'toHost': {'01-deny-all:app=web': {'01-deny-all:app=web':
                                                                            '01-deny-all:web'}}}}}
            # exclude irrelevant information
            del results_dict["runtimes"]
            del results_dict["results"]["raw-results"]
            # extract information from strings with random ids
            from_host = results_dict["results"]["mappings"]["fromHost"]["01-deny-all:app=web"]
            del results_dict["results"]["mappings"]["fromHost"]
            # compare the remaining dicts
            assert results_dict == expected_dict
            expected_start_string_1 = "01-deny-all:web-"
            assert from_host.startswith(expected_start_string_1)

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    res = subprocess.run(["kubectl", "delete", "-f", "e2e-manifests/01-deny-all-traffic-to-an-application.yml"],
                         capture_output=True,
                         timeout=60)

    assert res.returncode == 0
    print(res.stdout)
