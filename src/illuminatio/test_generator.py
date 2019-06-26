import time
from typing import List

import kubernetes as k8s
from illuminatio.k8s_util import labels_to_string
from illuminatio.rule import Rule
from illuminatio.test_case import NetworkTestCase
from illuminatio.host import ClusterHost, GenericClusterHost
from illuminatio.util import rand_port, INVERTED_ATTRIBUTE_PREFIX


class NetworkTestCaseGenerator:
    """ Class for Generating Test cases out of a k8s NetworkPolicy and saving them to a specified format. """

    logger = None

    def __init__(self, log):
        global logger
        logger = log

    def generate_test_cases(self, network_policies: List[k8s.client.V1NetworkPolicy],
                            namespaces: List[k8s.client.V1Namespace]):
        runtimes = {}
        start_time = time.time()
        isolated_hosts = []
        other_hosts = []
        outgoing_test_cases = []
        incoming_test_cases = []
        logger.debug("Generating test cases for " + str(network_policies))
        rules = [Rule.from_network_policy(netPol) for netPol in network_policies]
        net_pol_parsing_time = time.time()
        runtimes["parse"] = net_pol_parsing_time - start_time
        logger.debug("Rule: " + str(rules))
        for rule in rules:
            rule_host = ClusterHost(rule.concerns["namespace"], rule.concerns["podLabels"])
            if rule_host not in isolated_hosts:
                isolated_hosts.append(rule_host)
            if rule.allowed:  # means it is NOT default deny rule
                for connection in rule.allowed:
                    for port in connection.ports:
                        on_port = port
                        other_host = self._get_other_host_from(connection.targets, rule.concerns["namespace"])
                        other_hosts.append(other_host)
                        if connection.direction == "to":
                            case = NetworkTestCase(rule_host, other_host, on_port, True)
                            outgoing_test_cases.append(case)
                        elif connection.direction == "from":
                            case = NetworkTestCase(other_host, rule_host, on_port, True)
                            incoming_test_cases.append(case)
                        else:
                            raise ValueError("Direction '" + connection.direction + "' unknown!")
        positive_test_time = time.time()
        runtimes["positiveTestGen"] = positive_test_time - net_pol_parsing_time
        negative_test_cases, negative_test_gen_runtimes = self.generate_negative_cases_for_incoming_cases(
            isolated_hosts,
            incoming_test_cases,
            other_hosts, namespaces)
        runtimes["negativeTestGen"] = negative_test_gen_runtimes
        return outgoing_test_cases + negative_test_cases + incoming_test_cases, runtimes

    # TODO: implement it also for outgoing test cases
    def generate_negative_cases_for_incoming_cases(self, isolated_hosts, incoming_test_cases, other_hosts, namespaces):
        runtimes = {}
        start_time = time.time()
        namespace_labels = [h.namespace_labels for h in other_hosts if isinstance(h, GenericClusterHost)]
        namespaces_per_label_strings = {labels_to_string(k): [n.metadata.name for n in namespaces if
                                                              n.metadata.labels is not None
                                                              and k.items() <= n.metadata.labels.items()]
                                        for k in namespace_labels}
        namespace_label_resolve_time = time.time()
        runtimes["nsLabelResolve"] = namespace_label_resolve_time - start_time
        labels_per_namespace = {n.metadata.name: n.metadata.labels for n in namespaces}
        overlaps_per_host = {
            host: get_overlapping_hosts(host, namespaces_per_label_strings, labels_per_namespace,
                                        isolated_hosts + other_hosts)
            for host in isolated_hosts}
        overlap_calc_time = time.time()
        runtimes["overlapCalc"] = overlap_calc_time - namespace_label_resolve_time
        cases = []
        for host in isolated_hosts:
            host_string = str(host)
            host_start_time = time.time()
            runtimes[host_string] = {}
            # Check for hosts that can target these to construct negative cases from
            logger.debug(overlaps_per_host[host])
            reaching_hosts_with_ports = [(t.from_host, t.port_string) for t in incoming_test_cases if
                                         t.to_host in overlaps_per_host[host]]
            logger.debug(reaching_hosts_with_ports)
            reaching_host_find_time = time.time()
            runtimes[host_string]["findReachingHosts"] = reaching_host_find_time - host_start_time
            if reaching_hosts_with_ports:
                reaching_hosts, _ = zip(*reaching_hosts_with_ports)
                ports_per_host = {host: [p for h, p in reaching_hosts_with_ports if h == host] for host in
                                  reaching_hosts}
                match_all_host = GenericClusterHost({}, {})
                if match_all_host in reaching_hosts:
                    # All hosts are allowed to reach (on some ports or all) => results from ALLOW all
                    if "*" in ports_per_host[match_all_host]:
                        logger.info("Not generating negative tests for host " + str(
                            host) + " as all connections to it are allowed")
                    else:
                        case = NetworkTestCase(match_all_host, host, rand_port(ports_per_host[match_all_host]), False)
                        cases.append(case)
                    runtimes[host_string]["matchAllCase"] = time.time() - reaching_host_find_time
                else:
                    inverted_hosts = set([h for l in [invert_host(host) for host in reaching_hosts] for h in l])
                    hosts_on_inverted = {h: originalHost for l, originalHost in
                                         [(invert_host(host), host) for host in reaching_hosts] for h in l}
                    host_inversion_time = time.time()
                    runtimes[host_string]["hostInversion"] = host_inversion_time - reaching_host_find_time
                    overlaps_for_inverted_hosts = {
                        h: get_overlapping_hosts(h, namespaces_per_label_strings, labels_per_namespace, reaching_hosts)
                        for h in inverted_hosts}
                    overlap_calc_time = time.time()
                    runtimes[host_string]["overlapCalc"] = overlap_calc_time - host_inversion_time
                    logger.debug("InvertedHosts: " + str(inverted_hosts))
                    negative_test_targets = [h for h in inverted_hosts if len(overlaps_for_inverted_hosts[h]) <= 1]
                    logger.debug("NegativeTestTargets: " + str(negative_test_targets))
                    # now remove the inverted hosts that are reachable
                    for target in negative_test_targets:
                        ports_for_inverted_hosts_original_host = ports_per_host[hosts_on_inverted[target]]
                        if ports_for_inverted_hosts_original_host:
                            cases.append(
                                NetworkTestCase(target, host, ports_for_inverted_hosts_original_host[0], False))
                        else:
                            cases.append(NetworkTestCase(target, host, "*", False))
                    runtimes[host_string]["casesGen"] = time.time() - overlap_calc_time
            else:
                # No hosts are allowed to reach host -> it should be totally isolated
                # => results from default deny policy
                cases.append(NetworkTestCase(host, host, "*", False))
            runtimes["all"] = time.time() - start_time
        return cases, runtimes

    def _get_other_host_from(self, connection_targets, rule_namespace):
        namespace_labels = "namespaceLabels"
        pod_labels = "podLabels"
        namespace = "namespace"
        if namespace_labels in connection_targets and pod_labels in connection_targets:
            return GenericClusterHost(connection_targets[namespace_labels], connection_targets[pod_labels])
        elif namespace in connection_targets and pod_labels in connection_targets:
            return ClusterHost(connection_targets[namespace], connection_targets[pod_labels])
        elif namespace_labels in connection_targets:  # and no podLabels included
            return GenericClusterHost(connection_targets[namespace_labels], {})
        elif pod_labels in connection_targets:
            return ClusterHost(rule_namespace, connection_targets[pod_labels])
        elif connection_targets == {}:
            return GenericClusterHost({}, {})
        else:
            raise ValueError("Unknown combination of field in connection " + str(connection_targets))


def invert_host(host):
    if isinstance(host, GenericClusterHost):
        return invert_generic_cluster_host(host)
    if isinstance(host, ClusterHost):
        return invert_cluster_host(host)
    raise ValueError("Host " + str(host) + " is of unsupported type")


def invert_cluster_host(host: ClusterHost):
    if host.pod_labels == {}:
        return [ClusterHost(INVERTED_ATTRIBUTE_PREFIX + host.namespace, {})]

    inverted_hosts = [ClusterHost(INVERTED_ATTRIBUTE_PREFIX + host.namespace, host.pod_labels),
                      ClusterHost(INVERTED_ATTRIBUTE_PREFIX + host.namespace, invert_labels(host.pod_labels)),
                      ClusterHost(host.namespace, invert_labels(host.pod_labels))]
    return inverted_hosts


def invert_generic_cluster_host(host: GenericClusterHost):
    if host == GenericClusterHost({}, {}):
        raise ValueError("Cannot invert GenericClusterHost matching all hosts in cluster")
    elif host.namespace_labels == {}:
        return [GenericClusterHost({}, invert_labels(host.pod_labels))]
    else:
        inverted_hosts = [GenericClusterHost(host.namespace_labels, invert_labels(host.pod_labels)),
                          GenericClusterHost(invert_labels(host.namespace_labels), host.pod_labels),
                          GenericClusterHost(invert_labels(host.namespace_labels), invert_labels(host.pod_labels))]
        return inverted_hosts


def invert_labels(labels):
    return {INVERTED_ATTRIBUTE_PREFIX + k: v for k, v in labels.items()}


def get_overlapping_hosts(host, namespaces_per_label_strings, labels_per_namespace, other_hosts):
    """ Returns a list of hosts that *might* be selected by the same policies  """
    out = [host]
    for other in other_hosts:
        if host is not other:
            namespace_overlap = namespaces_overlap(host, namespaces_per_label_strings, labels_per_namespace, other)
            pod_label_overlap = labels_overlap(other.pod_labels, host.pod_labels)
            if namespace_overlap and pod_label_overlap:
                out.append(other)
    return out


def namespaces_overlap(host, namespaces_per_label_strings, labels_per_namespace, other):
    host_ns = resolve_namespaces(host, namespaces_per_label_strings)
    other_ns = resolve_namespaces(other, namespaces_per_label_strings)
    if host_ns and other_ns:
        return any(ns in other_ns for ns in host_ns)
    else:
        ns_labels = lookup_namespace_labels(host, labels_per_namespace)
        other_ns_labels = lookup_namespace_labels(other, labels_per_namespace)
        if ns_labels is not None and other_ns_labels is not None:
            return labels_overlap(ns_labels, other_ns_labels)
        else:  # if a namespace doesn't exist yet and we only have labels to match to a name it doesn't match
            return False


def labels_overlap(labels1, labels2):
    if labels1 and labels2:
        return any(item in labels2.items() for item in labels1.items())
    else:
        # if either of the labels dict is empty, they always overlap, as empty label selectors select all labels
        return True


def resolve_namespaces(host, namespaces_per_label_strings):
    logger.debug(host)
    if isinstance(host, ClusterHost):
        return [host.namespace]

    labels = labels_to_string(host.namespace_labels)
    return namespaces_per_label_strings[labels] if labels in namespaces_per_label_strings else []


def lookup_namespace_labels(host, labels_per_namespace):
    if isinstance(host, GenericClusterHost):
        return host.namespace_labels

    if host.namespace in labels_per_namespace:
        return labels_per_namespace[host.namespace]

    return None
