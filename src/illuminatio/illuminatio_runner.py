"""
This file contains the implementation of the illuminatio runner which
actively executes network policy tests inside the kubernetes cluster itself
"""

import json
import logging
import os
import subprocess
import socket
import tempfile
import time
from xml.etree import ElementTree
import yaml

import click
import click_log
import docker
from illuminatio.host import Host, ConcreteClusterHost
from illuminatio.k8s_util import init_test_output_config_map
import kubernetes as k8s

LOGGER = logging.getLogger(__name__)
click_log.basic_config(LOGGER)
CASE_FILE_PATH = "/etc/config/cases.yaml"


def build_result_string(port, target, should_be_blocked, was_blocked):
    """
    builds and returns a test result string
    """
    was_successful = should_be_blocked == was_blocked
    title = "Test " + target + ":" + ("-" if should_be_blocked else "") + port + (
        " succeeded" if was_successful else " failed")
    details = ("Could" + ("n't" if was_blocked else "") + " reach " + target + " on port " + port +
               ". Expected target to " + ("not " if should_be_blocked else "") + "be reachable")
    return title + "\n" + details


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
        store_results_to_cfg_map(results, namespace, name + "-results",
                                 {"overall": run_times["overall"], "tests": test_run_times})
    LOGGER.info("Finished running tests. Results:")
    LOGGER.info(results)
    # Sleep some time until container is killed. TODO: continuous mode ???
    time.sleep(60 * 60 * 24)


def run_all_tests():
    """
    Runs all tests,
    returns the results and measured execution times
    """
    pods_on_node = [ConcreteClusterHost(p.metadata.namespace, p.metadata.name) for p in get_pods_on_node().items]
    results = {}
    with open(CASE_FILE_PATH, "r") as yaml_file:
        cases = yaml.safe_load(yaml_file)
        LOGGER.debug("Cases: %s", str(cases))
        test_runtimes = {}
        all_sender_pods = [Host.from_identifier(from_host_string) for from_host_string in cases]
        sender_pods_on_node = get_pods_contained_in_both_lists(all_sender_pods, pods_on_node)
        # execute tests for each sender pod
        for sender_pod in sender_pods_on_node:
            pod_identifier = sender_pod.to_identifier()
            results[pod_identifier], test_runtimes[pod_identifier] = run_tests_for_sender_pod(sender_pod, cases)
    return results, test_runtimes


def get_pods_contained_in_both_lists(first_pod_list, second_pod_list):
    """
    Returns a list with pods contained in both given lists
    """
    sender_pods_on_node = [pod for pod in first_pod_list if pod_list_contains_pod(pod, second_pod_list)]
    return sender_pods_on_node


def run_tests_for_sender_pod(sender_pod, cases):
    """
    Runs a bunch of test cases from the network namespace of a given pod.
    """
    from_host_string = sender_pod.to_identifier()
    runtimes = {}
    nsenter_cmd = build_nsenter_cmd_for_pod(sender_pod.namespace, sender_pod.name)
    results = {}
    for target, ports in cases[from_host_string].items():
        start_time = time.time()
        results[target] = run_tests_for_target(nsenter_cmd, ports, target)
        runtimes[target] = time.time() - start_time
    return results, runtimes


def run_tests_for_target(enter_net_ns_cmd, ports, target):
    """
    This function executes the given command to jump into a desired network namespace
    from which it then does an nmap scan on several ports against a target.
    The results are converted from XML and returned as a dictionary.
    """
    # resolve host directly here
    # https://stackoverflow.com/questions/2805231/how-can-i-do-dns-lookups-in-python-including-referring-to-etc-hosts
    LOGGER.info("Target: %s", target)
    port_on_nums = {port.replace("-", ""): port for port in ports}
    port_string = ",".join(port_on_nums.keys())
    # ToDo do we really need this -> we know the service alreadz
    # DNS could be blocked
    # resolve target ip
    # Only IPv4 currently
    # ToDo try catch -- > socket.gaierror: [Errno -2] Name or service not known
    svc_dns_entry = get_domain_name_for(target)
    LOGGER.info(svc_dns_entry)
    svc_ip = socket.gethostbyname(svc_dns_entry)
    LOGGER.info("Service IP: %s for Service: %s", svc_ip, target)
    with tempfile.NamedTemporaryFile() as result_file:
        LOGGER.debug("Results will be stored to %s", result_file)
        # remove the need for nmap!
        # e.g. https://gist.github.com/betrcode/0248f0fda894013382d7
        # nmap that target TODO: handle None ip
        nmap_cmd = ["nmap", "-oX", result_file.name, "-Pn", "-p", port_string, svc_ip]
        cmd = enter_net_ns_cmd + nmap_cmd
        LOGGER.info("running nmap with cmd %s", cmd)
        prc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if prc.returncode:
            LOGGER.error("Executing nmap in foreign net ns failed! output:")
            LOGGER.error(prc.stderr)
            LOGGER.debug(prc)
            return {port_string: {"success": False,
                                  "error": "Couldn't nmap host {} with hostname {}".format(target, svc_dns_entry)}}

        LOGGER.info("finished running nmap")
        LOGGER.debug("Error log: %s", prc.stderr)
        # when not using shell the output from nmap contains \\n instead of newline characters
        LOGGER.info("Stdout: %s", str(prc.stdout).split("\\n"))
        return extract_results_from_nmap_xml_file(result_file, port_on_nums, target)


def pod_list_contains_pod(pod, pod_list):
    """
    Checks whether a list of pods contains a given pod
    """
    LOGGER.debug("Searching for pod %s", pod)
    if isinstance(pod, ConcreteClusterHost):
        is_on_node = any([pod == pod_on_node for pod_on_node in pod_list])
        if is_on_node:
            LOGGER.debug("Pod %s in namespace %s was found", str(pod.name), str(pod.namespace))
        else:
            LOGGER.debug("Pod %s in namespace %s isn't on this node", str(pod.name), str(pod.namespace))
        return is_on_node

    LOGGER.error("Found non-ConcreteClusterHost host in cases: %s", pod)
    return False


def extract_results_from_nmap_xml_file(result_file, port_on_nums, target):
    """
    Extracts the results of an nmap scan from an xml result file into a dictionary
    """
    xml = ElementTree.parse(result_file.name)
    hosts = [h for h in xml.getroot().iter("host")]
    if len(hosts) != 1:
        LOGGER.error(
            "Fund %s a single host in nmap results but expected only one target to be probed", str(len(hosts)))
        port_string = ",".join(port_on_nums.keys())
        return {
            port_string: {"success": False,
                          "error": "Found " + str(len(hosts)) + " hosts in nmap results, expected 1."}}
    host_element = hosts[0]
    host_names = [hn.get("name") for hn in host_element.iter("hostname")]
    LOGGER.debug("Found names %s for target %s", str(host_names), str(target))
    results = {}
    for port_element in host_element.iter("port"):
        port = port_element.get("portid")
        state = port_element.find("state").get("state")
        port_with_expectation = port_on_nums[port]
        should_be_blocked = "-" in port_with_expectation
        was_blocked = state == "filtered"
        results[port_with_expectation] = {}
        results[port_with_expectation]["success"] = should_be_blocked == was_blocked
        results[port_with_expectation]["string"] = build_result_string(port, target, should_be_blocked, was_blocked)
        results[port_with_expectation]["nmap-state"] = state
    return results


def get_domain_name_for(host_string):
    """ Replaces namespace:serviceName syntax with serviceName.namespace one,
        appending default as namespace if None exists """
    return ".".join(reversed((("" if ":" in host_string else "default:") + host_string).split(":")))


def get_docker_network_namespace(pod_namespace, pod_name):
    """
    Fetches and retrieves the network namespace information
    of a docker container running inside a desired pod
    """
    LOGGER.info("getting network namespace from docker")
    k8s.config.load_incluster_config()
    configuration = k8s.client.Configuration()
    api_instance = k8s.client.CoreV1Api(k8s.client.ApiClient(configuration))
    pretty = 'true'
    exact = False  # also retrieve the namespace
    export = False  # also retrieve unspecifiable fields (pod uid)
    pod = api_instance.read_namespaced_pod(pod_name, pod_namespace, pretty=pretty, exact=exact, export=export)
    pod_uid = pod.metadata.uid
    LOGGER.info("pod_uid: %s", pod_uid)
    if pod_uid is None:
        raise ValueError("Failed to retrieve pod uid")

    client = docker.from_env()
    LOGGER.info("fetching pause containers")
    pause_containers = client.containers.list(
        filters={"label": ["io.kubernetes.docker.type=podsandbox", "io.kubernetes.pod.uid="+pod_uid]})
    if len(pause_containers) != 1:
        raise ValueError("There should be only one pause container, found %d of them." % len(pause_containers))
    container = pause_containers[0]
    LOGGER.info("inspecting pause container")
    inspect = client.api.inspect_container(container.id)
    net_ns = inspect.get("NetworkSettings", {}).get("SandboxKey", {})
    if not net_ns:
        raise ValueError("Could not fetch Network Namespace from Docker Runtime.")
    return net_ns


def extract_network_namespace(inspectp_result):
    """
    Extracts the network namespace information from
    a 'crictl inspectp' result
    """
    json_object = json.loads(inspectp_result)
    net_ns = None
    for namespace in json_object["info"]["runtimeSpec"]["linux"]["namespaces"]:
        if namespace["type"] != "network":
            continue
        net_ns = namespace["path"]
        break
    return net_ns


def get_containerd_network_namespace(host_namespace, host_name):
    """
    Fetches and returns the path of the network namespace
    This function only works for runtimes that are CRI compliant e.g. containerd
    """
    cmd1 = ["crictl", "pods", "--name=" + str(host_name), "--namespace=" + str(host_namespace), "-q", "--no-trunc"]
    prc1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc1.returncode:
        LOGGER.error("Getting pods for name %s in namespace %s", str(host_name), str(host_namespace)
                     + " failed! output:")
        LOGGER.error(prc1.stderr)
    pod_id = prc1.stdout.strip()
    # ToDo error handling
    cmd2 = ["crictl", "inspectp", pod_id]
    prc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc2.returncode:
        LOGGER.error("Getting pods network namespace for pod %s failed! output:", str(pod_id))
        LOGGER.error(prc2.stderr)
    net_ns = extract_network_namespace(prc2.stdout)
    return net_ns


def build_nsenter_cmd_for_pod(pod_namespace, pod_name):
    """
    returns the entire nsenter command to jump into the pod's network namespace
    """
    container_runtime_name = os.environ["CONTAINER_RUNTIME_NAME"]
    if container_runtime_name == "containerd":
        net_ns = get_containerd_network_namespace(pod_namespace, pod_name)
    elif container_runtime_name == "docker":
        net_ns = get_docker_network_namespace(pod_namespace, pod_name)
    else:
        # TODO add more runtimes to support
        raise ValueError("the container runtime '%s' is not supported" % container_runtime_name)
    # make use of https://github.com/zalando/python-nsenter + ns_type netns should be enough
    # --> https://github.com/zalando/python-nsenter/blob/master/nsenter/__init__.py#L42-L45
    return ["nsenter", "-t", net_ns, "--net", "--"]


def get_pods_on_node():
    """
    Returns all pods on the node of the pod
    """
    hostname = os.environ.get("RUNNER_NODE")
    LOGGER.debug("RUNNER_NODE=%s", str(hostname))
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()
    # ToDo error handling!
    return api.list_pod_for_all_namespaces(field_selector="spec.nodeName==" + hostname)


def store_results_to_cfg_map(results, namespace, name, runtimes=None):
    """
    Writes given results into a ConfigMap
    """
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()

    LOGGER.info("Storing output to ConfigMap")
    cfg_map = init_test_output_config_map(namespace, name, data=yaml.dump(results))
    if runtimes:
        cfg_map.data["runtimes"] = yaml.dump(runtimes)
    config_map_in_cluster = api.list_namespaced_config_map(namespace, field_selector="metadata.name=" + name).items
    if config_map_in_cluster:
        api_response = api.patch_namespaced_config_map(name, namespace, cfg_map)
        LOGGER.info(api_response)
    else:
        api_response = api.create_namespaced_config_map(namespace, cfg_map)
        LOGGER.info(api_response)
