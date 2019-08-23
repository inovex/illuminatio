from os import path

import pytest
import re
import subprocess
import yaml
from kubernetes import client, config
from create_from_yaml import create_from_yaml

# TODO consider removing the raw stdout output of each test
REGEX_RESOURCE_INFIX = "[0-9a-z]{10}"
REGEX_RESOURCE_SUFFIX = "[0-9a-z]{5}"
REGEX_RESOURCE_LONG_SUFFIX = "%s[-]%s" % (REGEX_RESOURCE_INFIX, REGEX_RESOURCE_SUFFIX)


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


def create_resources_and_run_illuminatio(resource_manifest, results_yaml_file):
    config.load_kube_config()
    k8s_client = client.ApiClient()
    create_from_yaml(k8s_client, resource_manifest, wait_until_ready=True)
    # run illuminatio and store the results to a yaml file
    res = subprocess.run(["illuminatio", "clean", "run", "--runner-image=localhost:5000/illuminatio-runner:dev",
                          "-o", results_yaml_file],
                         capture_output=True,
                         timeout=120)
    assert res.returncode == 0


def cleanup_resources(resource_manifest):
    # delete illuminatio resources
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # delete test resources
    res = subprocess.run(["kubectl", "delete", "-f", resource_manifest],
                         capture_output=True,
                         timeout=120)

    assert res.returncode == 0
    print(res.stdout)


@pytest.mark.e2e
def test_deny_all_traffic_to_an_application():
    resource_manifest = "e2e-manifests/01-deny-all-traffic-to-an-application.yml"
    results_yaml_file = "result.yml"
    create_resources_and_run_illuminatio(resource_manifest, results_yaml_file)

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
            regex_expected_start_string_1 = re.compile("01[-]deny[-]all:web[-]%s" % REGEX_RESOURCE_LONG_SUFFIX)
            # not None if regex matches
            assert regex_expected_start_string_1.search(from_host_1)

    cleanup_resources(resource_manifest)


@pytest.mark.e2e
def test_limit_traffic_to_an_application():
    resource_manifest = "e2e-manifests/02-limit-traffic-to-an-application.yml"
    results_yaml_file = "result.yml"
    create_resources_and_run_illuminatio(resource_manifest, results_yaml_file)

    # evaluate the results of illuminatio

    with open(path.abspath(results_yaml_file)) as f:
        yaml_document = yaml.safe_load_all(f)
        for results_dict in yaml_document:
            validate_illuminatio_was_successful(results_dict)
            expected_dict_1 = {'cases': {'02-limit-traffic:app=bookstore': {
              '02-limit-traffic:role=api,app=bookstore': {'*': {'success': True}}},
              '02-limit-traffic:illuminatio-inverted-app=bookstore': {
              '02-limit-traffic:role=api,app=bookstore': {'-*': {'success': True}}},
              'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                '02-limit-traffic:role=api,app=bookstore': {'-*': {'success': True}}},
              'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
              '02-limit-traffic:role=api,app=bookstore': {'-*': {'success': True}}}},
              'results': {'mappings': {'ports': {'02-limit-traffic:app=bookstore': {
                '02-limit-traffic:role=api,app=bookstore': {'*': '80'}},
                '02-limit-traffic:illuminatio-inverted-app=bookstore': {
                '02-limit-traffic:role=api,app=bookstore': {'-*': '-80'}},
                'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                  '02-limit-traffic:role=api,app=bookstore': {'-*': '-80'}},
                'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
                    '02-limit-traffic:role=api,app=bookstore': {'-*': '-80'}}},
                    'toHost': {'02-limit-traffic:app=bookstore': {
                      '02-limit-traffic:role=api,app=bookstore': '02-limit-traffic:apiserver'},
                      '02-limit-traffic:illuminatio-inverted-app=bookstore': {
                        '02-limit-traffic:role=api,app=bookstore': '02-limit-traffic:apiserver'},
                      'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                          '02-limit-traffic:role=api,app=bookstore': '02-limit-traffic:apiserver'},
                      'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
                            '02-limit-traffic:role=api,app=bookstore': '02-limit-traffic:apiserver'}}}}}
            # same as dict above but with switched labels order
            expected_dict_2 = {'cases': {'02-limit-traffic:app=bookstore': {
              '02-limit-traffic:app=bookstore,role=api': {'*': {'success': True}}},
              '02-limit-traffic:illuminatio-inverted-app=bookstore': {
              '02-limit-traffic:app=bookstore,role=api': {'-*': {'success': True}}},
              'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                '02-limit-traffic:app=bookstore,role=api': {'-*': {'success': True}}},
              'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
              '02-limit-traffic:app=bookstore,role=api': {'-*': {'success': True}}}},
              'results': {'mappings': {'ports': {'02-limit-traffic:app=bookstore': {
                '02-limit-traffic:app=bookstore,role=api': {'*': '80'}},
                '02-limit-traffic:illuminatio-inverted-app=bookstore': {
                '02-limit-traffic:app=bookstore,role=api': {'-*': '-80'}},
                'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                  '02-limit-traffic:app=bookstore,role=api': {'-*': '-80'}},
                'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
                    '02-limit-traffic:app=bookstore,role=api': {'-*': '-80'}}},
                    'toHost': {'02-limit-traffic:app=bookstore': {
                      '02-limit-traffic:app=bookstore,role=api': '02-limit-traffic:apiserver'},
                      '02-limit-traffic:illuminatio-inverted-app=bookstore': {
                        '02-limit-traffic:app=bookstore,role=api': '02-limit-traffic:apiserver'},
                      'illuminatio-inverted-02-limit-traffic:app=bookstore': {
                          '02-limit-traffic:app=bookstore,role=api': '02-limit-traffic:apiserver'},
                      'illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore': {
                            '02-limit-traffic:app=bookstore,role=api': '02-limit-traffic:apiserver'}}}}}
            # exclude irrelevant information
            del results_dict["runtimes"]
            del results_dict["results"]["raw-results"]
            # extract information from strings with random ids
            from_host_dict = results_dict["results"]["mappings"]["fromHost"]
            from_host_1 = from_host_dict["02-limit-traffic:app=bookstore"]
            from_host_2 = from_host_dict["02-limit-traffic:illuminatio-inverted-app=bookstore"]
            from_host_3 = from_host_dict["illuminatio-inverted-02-limit-traffic:app=bookstore"]
            from_host_4 = from_host_dict["illuminatio-inverted-02-limit-traffic:illuminatio-inverted-app=bookstore"]
            del results_dict["results"]["mappings"]["fromHost"]
            # compare the remaining dicts
            assert results_dict == expected_dict_1 or results_dict == expected_dict_2
            regex_expected_start_string_1 = re.compile("02[-]limit[-]traffic:apiserver[-]%s" %
                                                       REGEX_RESOURCE_LONG_SUFFIX)
            regex_expected_start_string_2 = re.compile("02[-]limit[-]traffic:illuminatio-dummy-%s" %
                                                       REGEX_RESOURCE_SUFFIX)
            regex_expected_start_string_3 = re.compile(
              "illuminatio-inverted-02[-]limit[-]traffic:illuminatio-dummy-%s" % REGEX_RESOURCE_SUFFIX)
            regex_expected_start_string_4 = re.compile(
              "illuminatio-inverted-02[-]limit[-]traffic:illuminatio-dummy-%s" % REGEX_RESOURCE_SUFFIX)
            # not None if regex matches
            assert regex_expected_start_string_1.search(from_host_1)
            assert regex_expected_start_string_2.search(from_host_2)
            assert regex_expected_start_string_3.search(from_host_3)
            assert regex_expected_start_string_4.search(from_host_4)

    cleanup_resources(resource_manifest)
