import logging
import time
from os import path

import click
import click_log
import json
import kubernetes as k8s
import yaml
from illuminatio.cleaner import Cleaner
from illuminatio.test_generator import NetworkTestCaseGenerator
from illuminatio.test_orchestrator import NetworkTestOrchestrator
from illuminatio.util import CLEANUP_ALWAYS, CLEANUP_ON_REQUEST

logger = logging.getLogger(__name__)
click_log.basic_config(logger)

# ToDo do we really need here global variables?
orch = None
gen = None


@click.group(chain=True)
@click_log.simple_verbosity_option(logger, default="INFO")
@click.option('--incluster', default=False, is_flag=True)
def cli(incluster):
    global orch
    orch = NetworkTestOrchestrator([], logger)
    global gen
    gen = NetworkTestCaseGenerator(logger)
    if incluster:
        k8s.config.load_incluster_config()
    else:
        k8s.config.load_kube_config()


@cli.command()
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
    click.echo()
    runtimes = {}
    start_time = time.time()
    logger.info("Starting test generation and run.")
    core_api = k8s.client.CoreV1Api()
    # Fetch all pods, namespaces, services
    orch.set_runner_image(runner_image)
    orch.set_target_image(target_image)
    orch.refresh_cluster_resources(core_api)
    # Fetch all network policies
    v1net = k8s.client.NetworkingV1Api()
    net_pols = v1net.list_network_policy_for_all_namespaces()
    resource_pull_time = time.time()
    runtimes["resource-pull"] = resource_pull_time - start_time

    # Generate Test cases
    cases, gen_run_times = gen.generate_test_cases(net_pols.items, orch._current_namespaces)
    logger.info("Got cases: " + str(cases))
    case_time = time.time()
    case_duration = case_time - start_time
    runtimes["generate"] = case_duration
    render_cases(cases, case_duration)
    click.echo()
    if dry:
        click.echo("Skipping test exection as --dry was set")
        click.echo()
        return
    results, test_runtimes, additional_data, resource_creation_time, result_wait_time = execute_tests(cases)
    runtimes["resource-creation"] = resource_creation_time - case_time
    runtimes["result-waiting"] = result_wait_time - resource_creation_time
    result_time = time.time()
    result_duration = result_time - case_time
    runtimes["execute"] = result_duration
    runtimes["run"] = result_time - start_time
    if brief:
        simplyfy_successful_results(results)
    logger.info("TestResults: " + str(results))
    if outfile:
        # write output
        click.echo("Writing results to file " + outfile)
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
            logging.error("Output format " + extension + " not supported! Aborting write to file.")
    # echo results, whether they have been saved or not
    result_duration = result_time - case_time
    render_results(results, result_duration)
    # clean(True)
    click.echo()


def execute_tests(cases):
    # TODO: add a setter, initially the orchestrator was meant to be instantiated at this point,
    # but to pass click_logging's logger it was changed to be instantiated earlier
    orch._test_cases = cases
    core_api = k8s.client.CoreV1Api()
    from_host_mappings, to_host_mappings, port_mappings = orch.create_and_launch_daemon_set_runners(
        k8s.client.AppsV1Api(),
        core_api)
    resource_creation_time = time.time()
    raw_results, runtimes = orch.collect_results(core_api)
    result_collection_time = time.time()
    additional_data = {"raw-results": raw_results,
                       "mappings": {"fromHost": from_host_mappings, "toHost": to_host_mappings, "ports": port_mappings}}
    results = transform_results(raw_results, from_host_mappings, to_host_mappings, port_mappings)
    return results, runtimes, additional_data, resource_creation_time, result_collection_time


def transform_results(raw_results, from_host_mappings, to_host_mappings, port_mappings):
    transformed = {}
    logger.debug("Raw results:" + str(raw_results))
    logger.debug("fromHostMappings:" + str(from_host_mappings))
    logger.debug("toHostMappings:" + str(to_host_mappings))
    logger.debug("portMappings:" + str(port_mappings))
    for from_host, mapped_from_host in from_host_mappings.items():
        transformed[from_host] = {}
        for to_host, mapped_to_host in to_host_mappings[from_host].items():
            transformed[from_host][to_host] = {}
            for port, mapped_port in port_mappings[from_host][to_host].items():
                logger.debug("port: %s", port)
                logger.debug("mapped_port: " + str(mapped_port))
                logger.debug("from_host: " + str(from_host))
                logger.debug("to_host: " + str(to_host))
                logger.debug("mapped_from_host: " + str(mapped_from_host))
                logger.debug("mapped_to_host: " + str(mapped_to_host))
                logger.debug("raw_results: " + str(raw_results))
                # ToDo review here!
                if mapped_port in raw_results[mapped_from_host][mapped_to_host]:
                    transformed[from_host][to_host][port] = raw_results[mapped_from_host][mapped_to_host][mapped_port]
                else:
                    # handle missing ports when an error occurs by putting raw results with adjusted hosts
                    transformed[from_host][to_host] = raw_results[mapped_from_host][mapped_to_host]
                    break
    return transformed


def render_results(results, run_time, trailing_spaces=2):
    # ToDo store as configmap
    num_tests = len([p for f in results for t in results[f] for p in results[f][t]])
    # FIXME inconsistent use of log and click.echo
    click.echo("Finished running " + str(num_tests) + " tests in %.4f seconds" % run_time)
    if num_tests > 0:
        # this format expects 4 positional argument and a keyword widths argument w
        line_format = '{0:{w[0]}}{1:{w[1]}}{2:{w[2]}}{3:{w[3]}}'
        # then we compute the max string lengths for each layer of the result map separately
        w1 = max([len(f) for f in results])
        w2 = max([len(t) for f in results for t in results[f]])
        w3 = max([len(p) for f in results for t in results[f] for p in results[f][t]] + [len("PORT")])
        w4 = [w1, w2, w3, max(len(el) for el in ["success", "failure"])]
        # this is packed in our widths list, and trailingSpaces is added to each element
        widths = [w + trailing_spaces for w in w4]
        click.echo(line_format.format("FROM", "TO", "PORT", "RESULT", w=widths))
        for from_host in results:
            for to_host in results[from_host]:
                for port in results[from_host][to_host]:
                    success = results[from_host][to_host][port]["success"]
                    success_string = "success" if success else "failure"
                    if not success and "error" in results[from_host][to_host][port]:
                        success_string = "ERR: " + results[from_host][to_host][port]["error"]
                    click.echo(line_format.format(from_host, to_host, port, success_string, w=widths))


def render_cases(cases, run_time, trailing_spaces=2):
    # convert into tuples for character counting and printing
    case_string_tuples = [(c.from_host.to_identifier(), c.to_host.to_identifier(), c.port_string) for c in cases]
    # computes width (=max string length per column + trailingSpaces)
    widths = [max([len(el) for el in l]) + trailing_spaces for l in zip(*case_string_tuples)]
    # formats string to choose each elemt of the given tuple or array with the according width element
    line_format = '{0[0]:{w[0]}}{0[1]:{w[1]}}{0[2]:{w[2]}}'
    click.echo("Generated " + str(len(cases)) + " cases in %.4f seconds" % run_time)
    if len(cases) > 0:
        click.echo(line_format.format(("FROM", "TO", "PORT"), w=widths))
        for case in case_string_tuples:
            click.echo(line_format.format(case, w=widths))


def simplyfy_successful_results(results):
    for from_host in results:
        for to_host in results[from_host]:
            for port in results[from_host][to_host]:
                # here we effectifely strip every information but success from our results
                if results[from_host][to_host][port]["success"]:
                    results[from_host][to_host][port] = {"success": True}
                else:
                    results[from_host][to_host][port] = {"success": False}


@cli.command()
@click.option('--hard/--soft', default=True,
              help='Whether to delete all resources or only those with cleanup policy \'on_request\'.')
def clean(hard):
    clean_up_policies = [CLEANUP_ON_REQUEST, CLEANUP_ALWAYS] if hard else [CLEANUP_ALWAYS]
    logger.info("Starting cleaning resources with policies %s" % clean_up_policies)
    core_api = k8s.client.CoreV1Api()
    apps_api = k8s.client.AppsV1Api()
    rbac_api = k8s.client.RbacAuthorizationV1Api()
    cleaner = Cleaner(core_api, apps_api, rbac_api, logger)
    # clean up project namespaces, as they cascasde resource deletion
    for cleanup_val in clean_up_policies:
        cleaner.clean_up_namespaces(cleanup_val)
    # clean up resources in remaining ns
    namespace_list = core_api.list_namespace()
    namespaces = [ns.metadata.name for ns in namespace_list.items if
                  ns.metadata.name not in ["kube-system", "kube-public"]]
    for cleanup_val in clean_up_policies:
        cleaner.clean_up_daemon_sets_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_pods_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_services_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_cfg_maps_in_namespaces(namespaces, cleanup_val)
        cleaner.clean_up_cluster_role_binding(cleanup_val)
        cleaner.clean_up_service_accounts_in_namespaces(namespaces, cleanup_val)
    logger.info("Finished cleanUp")
