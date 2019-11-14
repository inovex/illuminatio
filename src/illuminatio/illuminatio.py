"""
This file contains the illuminatio CLI
"""

import logging
import time
from os import path
import json

import click
import click_log
import kubernetes as k8s
import yaml
from illuminatio.cleaner import Cleaner
from illuminatio.test_generator import NetworkTestCaseGenerator
from illuminatio.test_orchestrator import NetworkTestOrchestrator
from illuminatio.util import CLEANUP_ALWAYS, CLEANUP_ON_REQUEST
from termcolor import colored


LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)


@click.group(chain=True)
@click_log.simple_verbosity_option(LOGGER, default="INFO")
@click.option('--incluster', default=False, is_flag=True,
              help='Load credentials from kubernetes ServiceAccount. Cannot be used with --kubeconfig.')
@click.option('--kubeconfig', default=None, envvar='KUBECONFIG',
              help='Path to the kubeconfig file to use. Cannot be used with --incluster.')
def cli(incluster, kubeconfig):
    """
    CLI for testing kubernetes NetworkPolicies.
    """
    if incluster:
        k8s.config.load_incluster_config()
    else:
        try:
            k8s.config.load_kube_config(config_file=kubeconfig)
        except k8s.config.ConfigException as config_error:
            LOGGER.error(config_error)
            exit(1)
        except TypeError as type_error:
            LOGGER.error("Internal error: Couldn't load kubeconfig with error: %s", type_error)
            exit(1)


@cli.command(short_help='create and run test cases')
@click.option('-o', '--outfile', default=None,
              help='Output file to write results to. Format is chosen according to file ending. Supported: YAML, JSON')
@click.option('-b/-w', '--brief/--wordy', 'brief', default=True,
              help='Output file wordiness, wordy includes string representation of results')
@click.option('--dry', default=False, is_flag=True,
              help='Dry run only generates test cases without executing them.')
@click.option('-r', '--runner-image', default="inovex/illuminatio-runner:latest",
              help='Runner image used by illuminatio')
@click.option('-t', '--target-image', default="nginx:stable",
              help='Target image that is used to generate pods (should have a webserver inside listening on port 80)')
def run(outfile, brief, dry, runner_image, target_image):
    """
    Create and execute test cases for NetworkPolicies currently in cluster.
    """
    runtimes = {}
    start_time = time.time()
    LOGGER.info("Starting test generation and run.")
    core_api = k8s.client.CoreV1Api()
    orch = NetworkTestOrchestrator([], LOGGER)
    orch.set_runner_image(runner_image)
    orch.set_target_image(target_image)
    # Fetch all pods, namespaces, services
    orch.refresh_cluster_resources(core_api)
    v1net = k8s.client.NetworkingV1Api()
    # Fetch all network policies
    net_pols = v1net.list_network_policy_for_all_namespaces()
    runtimes["resource-pull"] = time.time() - start_time

    # Generate Test cases
    generator = NetworkTestCaseGenerator(LOGGER)
    cases, gen_run_times = generator.generate_test_cases(net_pols.items, orch.current_namespaces)
    LOGGER.debug("Got cases: %s", cases)
    case_time = time.time()
    runtimes["generate"] = case_time - start_time
    render_cases(cases, case_time - start_time)
    if dry:
        LOGGER.info("Skipping test execution as --dry was set")
        return

    if not cases:
        LOGGER.info("Skipping resource creation since no test were generated")
        return

    results, test_runtimes, additional_data, resource_creation_time, result_wait_time = execute_tests(cases, orch)
    runtimes["resource-creation"] = resource_creation_time - case_time
    runtimes["result-waiting"] = result_wait_time - resource_creation_time
    result_time = time.time()
    result_duration = result_time - case_time
    runtimes["execute"] = result_duration
    runtimes["run"] = result_time - start_time
    if brief:
        simplify_successful_results(results)
    LOGGER.debug("TestResults: %s", results)
    if outfile:
        # write output
        LOGGER.info("Writing results to file %s", outfile)
        _, extension = path.splitext(outfile)
        file_contents = {"cases": results, "runtimes": runtimes, "results": additional_data}
        file_contents["runtimes"]["runners"] = test_runtimes
        file_contents["runtimes"]["generator"] = gen_run_times
        if extension in [".yaml", ".yml"]:
            with open(outfile, 'w') as out:
                yaml.dump(file_contents, out, default_flow_style=False)
        elif extension == ".json":
            with open(outfile, 'w') as out:
                json.dump(file_contents, out)
        else:
            logging.error("Output format %s not supported! Aborting write to file.", extension)
    # echo results, whether they have been saved or not
    result_duration = result_time - case_time
    render_results(results, result_duration)
    # clean(True)


def execute_tests(cases, orch):
    """
    Executes all tests with given test cases
    """
    orch.test_cases = cases
    core_api = k8s.client.CoreV1Api()
    # namespace should be an argument !
    # -> illuminatio
    namespace_name = "illuminatio"

    if not orch.namespace_exists(namespace_name, core_api):
        orch.create_namespace(namespace_name, core_api)

    from_host_mappings, to_host_mappings, port_mappings, cfgmap = orch.ensure_cases_are_generated(core_api)
    pod_selector = orch.ensure_daemonset_is_ready(
        cfgmap,
        k8s.client.AppsV1Api(),
        core_api)
    resource_creation_time = time.time()
    raw_results, runtimes = orch.collect_results(pod_selector, core_api)
    result_collection_time = time.time()
    additional_data = {"raw-results": raw_results,
                       "mappings": {"fromHost": from_host_mappings, "toHost": to_host_mappings, "ports": port_mappings}}
    results = transform_results(raw_results, from_host_mappings, to_host_mappings, port_mappings)
    return results, runtimes, additional_data, resource_creation_time, result_collection_time


def transform_results(raw_results, sender_pod_mappings, receiver_pod_mappings, port_mappings):
    """
    Transforms all requests from raw into a more convenient format
    """
    transformed = {}
    LOGGER.debug("Raw results: %s", raw_results)
    LOGGER.debug("fromHostMappings: %s", sender_pod_mappings)
    LOGGER.debug("toHostMappings: %s", receiver_pod_mappings)
    LOGGER.debug("portMappings: %s", port_mappings)

    # iterate over all requests
    for sender_pod, mapped_sender_pod in sender_pod_mappings.items():
        transformed[sender_pod] = {}
        for receiver_pod, mapped_receiver_pod in receiver_pod_mappings[sender_pod].items():
            transformed[sender_pod][receiver_pod] = {}
            for port, mapped_port in port_mappings[sender_pod][receiver_pod].items():
                # fetch and print metadata for each request
                LOGGER.debug("port: %s", port)
                LOGGER.debug("mapped_port: %s", mapped_port)
                LOGGER.debug("sender_pod: %s", sender_pod)
                LOGGER.debug("receiver_pod: %s", receiver_pod)
                LOGGER.debug("mapped_sender_pod: %s", mapped_sender_pod)
                LOGGER.debug("mapped_receiver_pod: %s", mapped_receiver_pod)
                LOGGER.debug("raw_results: %s", raw_results)
                if mapped_port in raw_results[mapped_sender_pod][mapped_receiver_pod]:
                    # fetch all requests from desired ports
                    transformed[sender_pod][receiver_pod][port] = \
                        raw_results[mapped_sender_pod][mapped_receiver_pod][mapped_port]
                else:
                    # handle missing ports when an error occurs by putting raw results with adjusted pods
                    transformed[sender_pod][receiver_pod] = raw_results[mapped_sender_pod][mapped_receiver_pod]
                    break
    return transformed


def render_results(results, run_time, trailing_spaces=2):
    """
    Prints test results in a readable way
    """
    num_tests = len([p for f in results for t in results[f] for p in results[f][t]])
    LOGGER.info("\nFinished running %d tests in %.4f seconds", num_tests, run_time)
    if num_tests > 0:
        # this format expects 4 positional argument and a keyword widths argument w
        line_format = '{0:{w[0]}}{1:{w[1]}}{2:{w[2]}}{3:{w[3]}}'
        # then we compute the max string lengths for each layer of the result map separately
        width_1 = max([len(f) for f in results])
        width_2 = max([len(t) for f in results for t in results[f]])
        width_3 = max([len(p) for f in results for t in results[f] for p in results[f][t]] + [len("PORT")])
        width_4 = [width_1, width_2, width_3, max(len(el) for el in ["success", "failure"])]
        # this is packed in our widths list, and trailingSpaces is added to each element
        widths = [width + trailing_spaces for width in width_4]
        LOGGER.info(line_format.format("FROM", "TO", "PORT", "RESULT", w=widths))
        for from_host in results:
            for to_host in results[from_host]:
                for port in results[from_host][to_host]:
                    success = results[from_host][to_host][port]["success"]
                    success_string = "success" if success else "failure"
                    if not success and "error" in results[from_host][to_host][port]:
                        success_string = "ERR: %s" % results[from_host][to_host][port]["error"]

                    if success_string == "success":
                        success_string = colored(success_string, 'green')
                    else:
                        success_string = colored(success_string, 'red')

                    LOGGER.info(line_format.format(from_host, to_host, port, success_string, w=widths))


def render_cases(cases, run_time, trailing_spaces=2):
    """
    Prints test cases in a beautiful way
    """
    # convert into tuples for character counting and printing
    case_string_tuples = [(c.from_host.to_identifier(), c.to_host.to_identifier(), c.port_string) for c in cases]
    # computes width (=max string length per column + trailingSpaces)
    widths = [max([len(el) for el in l]) + trailing_spaces for l in zip(*case_string_tuples)]
    # formats string to choose each element of the given tuple or array with the according width element
    line_format = '{0[0]:{w[0]}}{0[1]:{w[1]}}{0[2]:{w[2]}}'
    LOGGER.info("Generated %d cases in %.4f seconds\n", len(cases), run_time)
    if cases:
        LOGGER.info(line_format.format(("FROM", "TO", "PORT"), w=widths))
        for case in case_string_tuples:
            LOGGER.info(line_format.format(case, w=widths))
    LOGGER.info("")


def simplify_successful_results(results):
    """
    Removes all information besides whether the run was successful from given results
    """
    for from_host in results:
        for to_host in results[from_host]:
            for port in results[from_host][to_host]:
                # here we effectifely strip every information but success from our results
                if results[from_host][to_host][port]["success"]:
                    results[from_host][to_host][port] = {"success": True}
                else:
                    results[from_host][to_host][port] = {"success": False}


@cli.command(short_help='delete test resources')
@click.option('--hard/--soft', default=True,
              help='Whether to delete all resources or only those with cleanup policy \'on_request\'.')
def clean(hard):
    """
    Delete resources created by illuminatio.
    """
    clean_up_policies = [CLEANUP_ON_REQUEST, CLEANUP_ALWAYS] if hard else [CLEANUP_ALWAYS]
    LOGGER.info("Starting cleaning resources with policies %s", clean_up_policies)
    core_api = k8s.client.CoreV1Api()
    apps_api = k8s.client.AppsV1Api()
    rbac_api = k8s.client.RbacAuthorizationV1Api()
    cleaner = Cleaner(core_api, apps_api, rbac_api, LOGGER)
    # clean up project namespaces, as they cascade resource deletion
    for cleanup_val in clean_up_policies:
        cleaner.clean_up_namespaces_with_cleanup_policy(cleanup_val)
    # clean up resources in remaining ns
    namespace_list = core_api.list_namespace()
    namespaces = [ns.metadata.name for ns in namespace_list.items if
                  ns.metadata.name not in ["kube-system", "kube-public"]]
    for cleanup_val in clean_up_policies:
        cleaner.clean_up_daemon_sets_in_namespaces_with_cleanup_policy(namespaces, cleanup_val)
        cleaner.clean_up_pods_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_services_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_cfg_maps_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_cluster_role_binding_with_cleanup_policy(cleanup_val)
        cleaner.clean_up_service_accounts_in_namespaces_with_cleanup_policy(namespaces, cleanup_val)
    LOGGER.info("Finished cleanUp")
