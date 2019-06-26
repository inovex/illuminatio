from xml.etree import ElementTree

import click
import json

import click_log
import kubernetes as k8s
import logging
import os
import subprocess
import socket
import tempfile
import time
import yaml
from illuminatio.host import Host, ConcreteClusterHost
from illuminatio.k8s_util import init_test_output_config_map
import docker

logger = logging.getLogger(__name__)
click_log.basic_config(logger)
case_file_path = "/etc/config/cases.yaml"


def build_result_string(port, target, should_be_blocked, was_blocked):
    was_successful = should_be_blocked == was_blocked
    title = "Test " + target + ":" + ("-" if should_be_blocked else "") + port + (
        " succeeded" if was_successful else " failed")
    details = ("Could" + ("n't" if was_blocked else "") + " reach " + target + " on port " + port +
               ". Expected target to " + ("not " if should_be_blocked else "") + "be reachable")
    return title + "\n" + details


@click.command()
@click_log.simple_verbosity_option(logger)
def cli():
    run_times = {"overall": "error"}
    if not os.path.exists(case_file_path):
        raise RuntimeError("Could not find cases.yaml in %s!" % case_file_path)
    results, test_run_times = run_all_tests()
    namespace = None
    name = None
    try:
        namespace = os.environ["RUNNER_NAMESPACE"]
        name = os.environ["RUNNER_NAME"]
    except KeyError:
        logger.error("Cannot store output to disk, as env vars are not set")
    logger.debug("Output EnvVars: RUNNER_NAMESPACE=%s, RUNNER_NAME=%s", namespace, name)
    if namespace is not None and name is not None:
        store_results_to_cfg_map(results, namespace, name + "-results",
                                 {"overall": run_times["overall"], "tests": test_run_times})
    logger.info("Finished running tests. Results:")
    logger.info(results)
    # Sleep some time until container is killed. TODO: continuous mode ???
    time.sleep(60 * 60 * 24)


def run_all_tests():
    pods_on_node = [ConcreteClusterHost(p.metadata.namespace, p.metadata.name) for p in get_pods_on_node().items]
    results = {}
    with open(case_file_path, "r") as yamlFile:
        cases = yaml.safe_load(yamlFile)
        logger.debug("Cases: " + str(cases))
        test_runtimes = {}
        all_from_pods = [Host.from_identifier(from_host_string) for from_host_string in cases]
        from_pods_on_node = filter_from_hosts(all_from_pods, pods_on_node)
        for from_pod in from_pods_on_node:
            pod_identifier = from_pod.to_identifier()
            results[pod_identifier], test_runtimes[pod_identifier] = run_tests_for_from_pod(from_pod, cases)
    return results, test_runtimes


def filter_from_hosts(from_hosts, pods_on_node):
    from_hosts_on_node = [host for host in from_hosts if host_on_node(host, pods_on_node)]
    return from_hosts_on_node


def run_tests_for_from_pod(from_pod, cases):
    from_host_string = from_pod.to_identifier()
    runtimes = {}
    nsenter_cmd = build_nsenter_cmd_for_pod(from_pod.namespace, from_pod.name)
    results = {}
    for target, ports in cases[from_host_string].items():
        start_time = time.time()
        results[target] = run_tests_for_target(nsenter_cmd, ports, target)
        runtimes[target] = time.time() - start_time
    return results, runtimes


def run_tests_for_target(enter_net_ns_cmd, ports, target):
    # resolve host directly here
    # https://stackoverflow.com/questions/2805231/how-can-i-do-dns-lookups-in-python-including-referring-to-etc-hosts
    logger.info("Target: %s" % target)
    port_on_nums = {port.replace("-", ""): port for port in ports}
    port_string = ",".join(port_on_nums.keys())
    # ToDo do we really need this -> we know the service alreadz
    # DNS could be blocked
    # resolve target ip
    # Only IPv4 curretnly
    # ToDo try catch -- > socket.gaierror: [Errno -2] Name or service not known
    svc_dns_entry = get_domain_name_for(target)
    logger.info(svc_dns_entry)
    svc_ip = socket.gethostbyname(svc_dns_entry)
    logger.info(svc_ip)

    """
        logger.error("Resolving host resulted in an error: " + str(resolve_host_prc.stdout))
        return {port_string: {"success": False,
                              "error": "Couldn't resolve host '" + str(
                                  target) + "' with hostname " + str(
                                  get_domain_name_for(target))}}
    """
    logger.info("Service IP: %s for Service: %s", svc_ip, target)
    with tempfile.NamedTemporaryFile() as result_file:
        logger.debug("Results will be stored to %s", result_file)
        # remove the need for nmap!
        # e.g. https://gist.github.com/betrcode/0248f0fda894013382d7
        # nmap that target TODO: handle None ip
        nmap_cmd = ["nmap", "-oX", result_file.name, "-Pn", "-p", port_string, svc_ip]
        cmd = enter_net_ns_cmd + nmap_cmd
        logger.info("running nmap with cmd %s", cmd)
        prc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if prc.returncode:
            logger.error("Executing nmap in foreign net ns failed! output:")
            logger.error(prc.stderr)
            logger.debug(prc)
            return {port_string: {"success": False,
                                  "error": "Couldn't nmap host {} with hostname {}".format(target, svc_dns_entry)}}

        logger.info("finished running nmap")
        logger.debug("Error log: %s", prc.stderr)
        # when not using shell the output from nmap contains \\n instead of newline characters
        logger.info("Stdout: %s", str(prc.stdout).split("\\n"))
        return extract_results_from_nmap_xml_file(result_file, port_on_nums, target)


def host_on_node(host, pods_on_node):
    logger.debug("Searching for host %s", host)
    if isinstance(host, ConcreteClusterHost):
        is_on_node = any([host == pod for pod in pods_on_node])
        logger.debug(
            "Pod " + str(host.name) + " in namespace " + str(host.namespace) + (
                " was found" if is_on_node else " isn't on this node"))
        return is_on_node

    logger.error("Found non-ConcreteClusterHost host in cases: %s", host)
    return False


def extract_results_from_nmap_xml_file(result_file, port_on_nums, target):
    xml = ElementTree.parse(result_file.name)
    hosts = [h for h in xml.getroot().iter("host")]
    if len(hosts) != 1:
        logger.error(
            "Fund " + str(len(hosts)) + " a single host in nmap results but expected only one target to be probed")
        port_string = ",".join(port_on_nums.keys())
        return {
            port_string: {"success": False,
                          "error": "Found " + str(len(hosts)) + " hosts in nmap results, expected 1."}}
    else:
        host_element = hosts[0]
        host_names = [hn.get("name") for hn in host_element.iter("hostname")]
        logger.debug("Found names " + str(host_names) + " for target " + str(target))
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
    logger.info("getting network namespace from docker")
    k8s.config.load_incluster_config()
    configuration = k8s.client.Configuration()
    api_instance = k8s.client.CoreV1Api(k8s.client.ApiClient(configuration))
    pretty = 'true'
    exact = False  # also retrieve the namespace
    export = False  # also retrieve unspecifiable fields (pod uid)
    pod = api_instance.read_namespaced_pod(pod_name, pod_namespace, pretty=pretty, exact=exact, export=export)
    pod_uid = pod.metadata.uid
    logger.info("pod_uid: " + pod_uid)
    if pod_uid is None:
        raise ValueError("Failed to retrieve pod uid")

    client = docker.from_env()
    logger.info("fetching pause containers")
    pause_containers = client.containers.list(
        filters={"label": ["io.kubernetes.docker.type=podsandbox", "io.kubernetes.pod.uid="+pod_uid]})
    if len(pause_containers) != 1:
        raise ValueError("There should be only one pause container, found %d of them." % len(pause_containers))
    container = pause_containers[0]
    logger.info("inspecting pause container")
    inspect = client.api.inspect_container(container.id)
    net_ns = inspect.get("NetworkSettings", {}).get("SandboxKey", {})
    if not net_ns:
        raise ValueError("Could not fetch Network Namespace from Docker Runtime.")
    return net_ns


def get_network_namespace_from(inspectp_result):
    js = json.loads(inspectp_result)
    net_ns = None
    for ns in js["info"]["runtimeSpec"]["linux"]["namespaces"]:
        if ns["type"] != "network":
            continue
        net_ns = ns["path"]
        break
    return net_ns


def get_containerd_network_namespace(host_namespace, host_name):
    cmd1 = ["crictl", "pods", "--name=" + str(host_name), "--namespace=" + str(host_namespace), "-q", "--no-trunc"]
    prc1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc1.returncode:
        logger.error("Getting pods for name " + str(host_name) + " in namespace " + str(host_namespace)
                     + " failed! output:")
        logger.error(prc1.stderr)
    pod_id = prc1.stdout.strip()
    # ToDo error handling
    cmd2 = ["crictl", "inspectp", pod_id]
    prc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if prc2.returncode:
        logger.error("Getting pods network namespace for pod " + str(pod_id) + " failed! output:")
        logger.error(prc2.stderr)
    net_ns = get_network_namespace_from(prc2.stdout)
    return net_ns


def build_nsenter_cmd_for_pod(pod_namespace, pod_name):
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
    hostname = os.environ.get("RUNNER_NODE")
    logger.debug("RUNNER_NODE=" + str(hostname))
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()
    # ToDo error handling!
    return api.list_pod_for_all_namespaces(field_selector="spec.nodeName==" + hostname)


def store_results_to_cfg_map(results, namespace, name, runtimes=None):
    k8s.config.load_incluster_config()
    api = k8s.client.CoreV1Api()

    logger.info("Storing output to ConfigMap")
    cfg_map = init_test_output_config_map(namespace, name, data=yaml.dump(results))
    if runtimes:
        cfg_map.data["runtimes"] = yaml.dump(runtimes)
    config_map_in_cluster = api.list_namespaced_config_map(namespace, field_selector="metadata.name=" + name).items
    if config_map_in_cluster:
        api_response = api.patch_namespaced_config_map(name, namespace, cfg_map)
        logger.info(api_response)
    else:
        api_response = api.create_namespaced_config_map(namespace, cfg_map)
        logger.info(api_response)
