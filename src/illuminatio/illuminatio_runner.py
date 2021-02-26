"""
This file contains the implementation of the illuminatio runner which
actively executes network policy tests inside the kubernetes cluster itself
"""
import ipaddress
import json
import logging
import os
import subprocess
import time
import platform
import yaml
import nmap

import click
import click_log
import docker
import kubernetes as k8s

from illuminatio.host import Host, ConcreteClusterHost
from illuminatio.k8s_util import create_test_output_config_map_manifest

# Otherwise we get an error on Mac
if platform.system() == "Linux":
    from nsenter import Namespace

LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)
CASE_FILE_PATH = "/etc/config/cases.yaml"


def build_result_string(port, target, should_be_blocked, was_blocked):
    """
    Builds and returns a test result string
    """
    was_successful = should_be_blocked == was_blocked
    title = "Test %s:%s%s%s" % (
        target,
        ("-" if should_be_blocked else ""),
        port,
        (" succeeded" if was_successful else " failed"),
    )
    details = ("Could%s reach %s on port %s. Expected target to %sbe reachable") % (
        ("n't" if was_blocked else ""),
        target,
        port,
        ("not " if should_be_blocked else ""),
    )
    return f"{title}\n{details}"


@click.command()
@click_log.simple_verbosity_option(LOGGER)
def cli():
    """
    Command Line function which runs all tests and stores the results into a ConfigMap.
    """
    run_times = {"overall": "error"}
    if not os.path.exists(CASE_FILE_PATH):
        raise RuntimeError("Could not find cases.yaml in %s!" % CASE_FILE_PATH)
    results, test_run_times = run_all_tests()
    namespace = None
    name = None
    try:
        namespace = os.environ["RUNNER_NAMESPACE"]
        name = os.environ["RUNNER_NAME"]
    except KeyError:
        LOGGER.error("Could not store output to ConfigMap, as env vars are not set")
    LOGGER.debug("Output EnvVars: RUNNER_NAMESPACE=%s, RUNNER_NAME=%s", namespace, name)
    if namespace is not None and name is not None:
        store_results_to_cfg_map(
            results,
            namespace,
            "%s-results" % name,
            {"overall": run_times["overall"], "tests": test_run_times},
        )
    LOGGER.info("Finished running tests. Results:")
    LOGGER.info(results)
    # Sleep some time until container is killed. TODO: continuous mode ???
    # TODO we should watch for ConfigMap changes and restart the test cases
    time.sleep(60 * 60 * 24)


def run_all_tests():
    """
    Runs all tests,
    returns the results and measured execution times
    """
    pods_on_node = [
        ConcreteClusterHost(p.metadata.namespace, p.metadata.name)
        for p in get_pods_on_node().items
    ]
    results = {}
    with open(CASE_FILE_PATH, "r") as yaml_file:
        cases = yaml.safe_load(yaml_file)
        LOGGER.debug("Cases: %s", cases)
        test_runtimes = {}
        all_sender_pods = [
            Host.from_identifier(from_host_string) for from_host_string in cases
        ]
        sender_pods_on_node = get_pods_contained_in_both_lists(
            all_sender_pods, pods_on_node
        )
        # execute tests for each sender pod
        for sender_pod in sender_pods_on_node:
            pod_identifier = sender_pod.to_identifier()
            (
                results[pod_identifier],
                test_runtimes[pod_identifier],
            ) = run_tests_for_sender_pod(sender_pod, cases)
    return results, test_runtimes


def get_pods_contained_in_both_lists(sender_pods, pods_on_node):
    """
    Returns a list with pods contained in both given lists
    """
    # TODO: do this is a more performant way, e.g. convert one list into a dict
    sender_pods_on_node = [
        pod for pod in sender_pods if pod_list_contains_pod(pod, pods_on_node)
    ]
    return sender_pods_on_node


def pod_list_contains_pod(pod, pod_list):
    """
    Checks whether a list of pods contains a given pod
    """
    LOGGER.debug("Searching for pod %s", pod)
    if isinstance(pod, ConcreteClusterHost):
        is_on_node = any([pod == pod_on_node for pod_on_node in pod_list])
        if is_on_node:
            LOGGER.debug("Pod %s in namespace %s was found", pod.name, pod.namespace)
        else:
            LOGGER.debug(
                "Pod %s in namespace %s isn't on this node", pod.name, pod.namespace
            )
        return is_on_node

    LOGGER.error("Found non-ConcreteClusterHost host in cases: %s", pod)
    return False


def run_tests_for_sender_pod(sender_pod, cases):
    """
    Runs test cases from the network namespace of a given pod.
    """
    from_host_string = sender_pod.to_identifier()
    runtimes = {}
    network_ns = get_network_ns_of_pod(sender_pod.namespace, sender_pod.name)
    # TODO check if network ns is None -> HostNetwork is set
    results = {}
    for target, ports in cases[from_host_string].items():
        start_time = time.time()
        results[target] = run_tests_for_target(network_ns, ports, target)
        runtimes[target] = time.time() - start_time
    return results, runtimes


def run_tests_for_target(network_ns, ports, target):
    """
    Enters a desired network namespace and attempts to reach a target on a list of ports.
    """
    # resolve host directly here
    # https://stackoverflow.com/questions/2805231/how-can-i-do-dns-lookups-in-python-including-referring-to-etc-hosts
    LOGGER.info("Target: %s", target)
    port_on_nums = {port.replace("-", ""): port for port in ports}
    port_string = ",".join(port_on_nums.keys())

    ipv6_arg = ""
    if ipaddress.ip_address(target).version == 6:
        ipv6_arg = "-6"

    nm_scanner = nmap.PortScanner()
    with Namespace(network_ns, "net"):
        nm_scanner.scan(target, arguments=f"-n -Pn -p {port_string} {ipv6_arg}")
    LOGGER.info("Ran nmap with cmd %s", nm_scanner.command_line())

    return extract_results_from_nmap(nm_scanner, port_on_nums, target)


def extract_results_from_nmap(nmap_res, port_on_nums, target):
    """
    Extracts the results of an nmap scan into a dictionary
    """
    hosts = nmap_res.all_hosts()
    if len(hosts) != 1:
        port_string = ",".join(port_on_nums.keys())
        return {
            port_string: {
                "success": False,
                "error": f"Found {len(hosts)} hosts in nmap results, expected 1.",
            }
        }

    results = {}

    host = hosts[0]
    for proto in nmap_res[host].all_protocols():
        # get all scanned ports for all protocols
        for port in nmap_res[host][proto].keys():
            if proto == "tcp":
                # We use the direct tcp method here for better mocking
                state = nmap_res[host].tcp(port)["state"]
            else:
                state = nmap_res[host][proto][port]["state"]
            port_with_expectation = port_on_nums[str(port)]
            should_be_blocked = "-" in port_with_expectation
            was_blocked = state == "filtered"
            results[port_with_expectation] = {
                "success": should_be_blocked == was_blocked,
                "string": build_result_string(
                    port, target, should_be_blocked, was_blocked
                ),
                "nmap-state": state,
            }

    return results


def get_domain_name_for(host_string):
    """
    Replaces namespace:serviceName syntax with serviceName.namespace one,
    appending default as namespace if None exists
    """
    return ".".join(
        reversed(
            ("%s%s" % (("" if ":" in host_string else "default:"), host_string)).split(
                ":"
            )
        )
    )


def get_docker_network_namespace(pod_namespace, pod_name):
    """
    Fetches and retrieves the network namespace information
    of a docker container running inside a desired pod
    """
    LOGGER.info("getting network namespace from docker")
    k8s.config.load_incluster_config()
    configuration = k8s.client.Configuration()
    api_instance = k8s.client.CoreV1Api(k8s.client.ApiClient(configuration))
    pretty = "true"
    exact = False  # also retrieve the namespace
    export = False  # also retrieve unspecifiable fields (pod uid)
    pod = api_instance.read_namespaced_pod(
        pod_name, pod_namespace, pretty=pretty, exact=exact, export=export
    )
    pod_uid = pod.metadata.uid
    LOGGER.info("pod_uid: %s", pod_uid)
    if pod_uid is None:
        raise ValueError("Failed to retrieve pod uid")

    client = docker.from_env()
    LOGGER.info("fetching pause containers")
    pause_containers = client.containers.list(
        filters={
            "label": [
                "io.kubernetes.docker.type=podsandbox",
                "io.kubernetes.pod.uid=%s" % pod_uid,
            ]
        }
    )
    if len(pause_containers) != 1:
        raise ValueError(
            "There should be only one pause container, found %d of them."
            % len(pause_containers)
        )
    container = pause_containers[0]
    LOGGER.info("inspecting pause container")
    inspect = client.api.inspect_container(container.id)
    net_ns = inspect.get("NetworkSettings", {}).get("SandboxKey", {})
    if not net_ns:
        raise ValueError("Could not fetch Network Namespace from Docker Runtime.")
    return net_ns


def extract_cri_network_namespace(inspectp_result):
    """
    Extracts the the path of the network namespace of a pod's crictl inspectp output.
    """
    json_object = json.loads(inspectp_result)
    net_ns = None
    for namespace in json_object["info"]["runtimeSpec"]["linux"]["namespaces"]:
        if namespace["type"] != "network":
            continue
        net_ns = namespace["path"]
        break

    return net_ns


def get_cri_network_namespace(host_namespace, host_name):
    """
    Fetches and returns the path of the network namespace
    This function only works for runtimes that are CRI compliant e.g. containerd
    """
    cmd1 = [
        "crictl",
        "pods",
        "--name=%s" % str(host_name),
        "--namespace=%s" % str(host_namespace),
        "-q",
        "--no-trunc",
    ]
    prc1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc1.returncode:
        LOGGER.error(
            "Getting pods for name %s in namespace %s failed! output:",
            host_name,
            host_namespace,
        )
        LOGGER.error(prc1.stderr)
    pod_id = prc1.stdout.strip()
    # ToDo error handling
    cmd2 = ["crictl", "inspectp", pod_id]
    prc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc2.returncode:
        LOGGER.error(
            "Getting pods network namespace for pod %s failed! output:", pod_id
        )
        LOGGER.error(prc2.stderr)

    return extract_cri_network_namespace(prc2.stdout)


def get_network_ns_of_pod(pod_namespace, pod_name):
    """
    Returns the network namespace of a pod
    """
    container_runtime_name = os.environ["CONTAINER_RUNTIME_NAME"]
    if container_runtime_name == "containerd":
        net_ns = get_cri_network_namespace(pod_namespace, pod_name)
    elif container_runtime_name == "docker":
        net_ns = get_docker_network_namespace(pod_namespace, pod_name)
    else:
        # TODO add more runtimes to support
        raise ValueError(
            "the container runtime '%s' is not supported" % container_runtime_name
        )

    return net_ns


def get_pods_on_node():
    """
    Returns all pods on the node of this pod
    """
    hostname = os.environ.get("RUNNER_NODE")
    LOGGER.debug("RUNNER_NODE=%s", hostname)
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()
    # ToDo error handling!
    return api.list_pod_for_all_namespaces(
        field_selector="spec.nodeName==%s" % hostname
    )


def store_results_to_cfg_map(results, namespace, name, runtimes=None):
    """
    Writes given results into a ConfigMap
    """
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()

    LOGGER.info("Storing output to ConfigMap")
    cfg_map = create_test_output_config_map_manifest(
        namespace, name, data=yaml.dump(results)
    )
    if runtimes:
        cfg_map.data["runtimes"] = yaml.dump(runtimes)
    try:
        api.read_namespaced_config_map(name, namespace)
        api_response = api.patch_namespaced_config_map(name, namespace, cfg_map)
        LOGGER.info(api_response)
    except k8s.client.rest.ApiException as api_exception:
        if api_exception.reason != "Not Found":
            raise api_exception
        api_response = api.create_namespaced_config_map(namespace, cfg_map)
        LOGGER.info(api_response)
