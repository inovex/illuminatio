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
    manifest = "e2e-manifests/01-deny-all-traffic-to-an-application.yml"
    create_from_yaml(k8s_client, manifest, verbose=False, wait_until_ready=True)
    results_yaml_file = "result.yml"
    # run illuminatio and store the results to a yaml file
    res = subprocess.run(["illuminatio", "clean", "run", "--runner-image=localhost:5000/illuminatio-runner:dev",
                          "-o", results_yaml_file],
                         capture_output=True,
                         timeout=120)
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
            from_host_dict = results_dict["results"]["mappings"]["fromHost"]
            from_host_1 = from_host_dict["01-deny-all:app=web"]
            del results_dict["results"]["mappings"]["fromHost"]
            # compare the remaining dicts
            assert results_dict == expected_dict
            regex_pod_suffix = "[0-9a-z]{10}[-][0-9a-z]{5}"
            regex_expected_start_string_1 = re.compile("01[-]deny[-]all:web[-]" + regex_pod_suffix)
            # not None if regex matches
            assert regex_expected_start_string_1.search(from_host_1)

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    res = subprocess.run(["kubectl", "delete", "-f", manifest],
                         capture_output=True,
                         timeout=60)

    assert res.returncode == 0
    print(res.stdout)

@pytest.mark.e2e
def test_limit_traffic_to_an_application():
    config.load_kube_config()
    k8s_client = client.ApiClient()
    manifest = "e2e-manifests/02-limit-traffic-to-an-application.yml"
    create_from_yaml(k8s_client, manifest, verbose=False, wait_until_ready=True)
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
            expected_dict = {'cases': {'default:app=bookstore': {'default:app=bookstore,role=api': {'*': {'success': True}}}, 'default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': {'-*': {'success': True}}}, 'illuminatio-inverted-default:app=bookstore': {'default:app=bookstore,role=api': {'-*': {'success': True}}}, 'illuminatio-inverted-default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': {'-*': {'success': True}}}}, 'results': {'mappings': {'ports': {'default:app=bookstore': {'default:app=bookstore,role=api': {'*': '80'}}, 'default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': {'-*': '-80'}}, 'illuminatio-inverted-default:app=bookstore': {'default:app=bookstore,role=api': {'-*': '-80'}}, 'illuminatio-inverted-default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': {'-*': '-80'}}}, 'toHost': {'default:app=bookstore': {'default:app=bookstore,role=api': 'default:apiserver'}, 'default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': 'default:apiserver'}, 'illuminatio-inverted-default:app=bookstore': {'default:app=bookstore,role=api': 'default:apiserver'}, 'illuminatio-inverted-default:illuminatio-inverted-app=bookstore': {'default:app=bookstore,role=api': 'default:apiserver'}}}}}
            # exclude irrelevant information
            del results_dict["runtimes"]
            del results_dict["results"]["raw-results"]
            # extract information from strings with random ids
            from_host_dict = results_dict["results"]["mappings"]["fromHost"]
            from_host_1 = from_host_dict["default:app=bookstore"]
            from_host_2 = from_host_dict["default:illuminatio-inverted-app=bookstore"]
            from_host_3 = from_host_dict["illuminatio-inverted-default:app=bookstore"]
            from_host_4 = from_host_dict["illuminatio-inverted-default:illuminatio-inverted-app=bookstore"]
            del results_dict["results"]["mappings"]["fromHost"]
            # compare the remaining dicts
            assert results_dict == expected_dict
            regex_pod_suffix = "[0-9a-z]{10}[-][0-9a-z]{5}"
            regex_expected_start_string_1 = re.compile("default:apiserver[-]" + regex_pod_suffix)
            regex_expected_start_string_2 = re.compile("default:illuminatio-dummy-[0-9a-z]{5}")
            regex_expected_start_string_3 = re.compile("illuminatio-inverted-default:illuminatio-dummy-[0-9a-z]{5}")
            regex_expected_start_string_4 = re.compile("illuminatio-inverted-default:illuminatio-dummy-[0-9a-z]{5}")
            # not None if regex matches
            assert regex_expected_start_string_1.search(from_host_1)
            assert regex_expected_start_string_2.search(from_host_2)
            assert regex_expected_start_string_3.search(from_host_3)
            assert regex_expected_start_string_4.search(from_host_4)

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    res = subprocess.run(["kubectl", "delete", "-f", manifest],
                         capture_output=True,
                         timeout=60)

    assert res.returncode == 0
    print(res.stdout)
