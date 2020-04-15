"""
File for test case generation
"""
import time
from typing import List

import kubernetes as k8s
from illuminatio.k8s_util import labels_to_string
from illuminatio.rule import Rule
from illuminatio.test_case import NetworkTestCase
from illuminatio.host import ClusterHost, GenericClusterHost
from illuminatio.util import rand_port, INVERTED_ATTRIBUTE_PREFIX


def _get_other_host_from(connection_targets, rule_namespace):
    namespace_labels = "namespaceLabels"
    pod_labels = "podLabels"
    namespace = "namespace"
    if namespace_labels in connection_targets and pod_labels in connection_targets:
        return GenericClusterHost(
            connection_targets[namespace_labels], connection_targets[pod_labels]
        )
    if namespace in connection_targets and pod_labels in connection_targets:
        return ClusterHost(
            connection_targets[namespace], connection_targets[pod_labels]
        )
    if namespace_labels in connection_targets:  # and no podLabels included
        return GenericClusterHost(connection_targets[namespace_labels], {})
    if pod_labels in connection_targets:
        return ClusterHost(rule_namespace, connection_targets[pod_labels])
    if connection_targets == {}:
        return GenericClusterHost({}, {})
    raise ValueError(
        "Unknown combination of field in connection %s" % connection_targets
    )


def get_namespace_label_strings(namespace_labels, namespaces):
    """
    Returns a set of all stringified namespace labels
    """
    # list of all namespace names with labels
    return {
        labels_to_string(namespace_label): [
            namespace.metadata.name
            for namespace in namespaces
            if namespace.metadata.labels is not None
            and namespace_label.items() <= namespace.metadata.labels.items()
        ]
        for namespace_label in namespace_labels
    }


class NetworkTestCaseGenerator:
    """
    Class for Generating Test cases out of a k8s NetworkPolicy and saving them to a specified format
    """

    def __init__(self, log):
        self.logger = log

    def generate_test_cases(
        self,
        network_policies: List[k8s.client.V1NetworkPolicy],
        namespaces: List[k8s.client.V1Namespace],
    ):
        """
        Generates positive and negative test cases, also returns measured runtimes
        """
        runtimes = {}
        start_time = time.time()
        isolated_hosts = []
        other_hosts = []
        outgoing_test_cases = []
        incoming_test_cases = []
        self.logger.debug("Generating test cases for %s", network_policies)
        rules = [Rule.from_network_policy(netPol) for netPol in network_policies]
        net_pol_parsing_time = time.time()
        runtimes["parse"] = net_pol_parsing_time - start_time
        self.logger.debug("Rule: %s", rules)
        for rule in rules:
            rule_host = ClusterHost(
                rule.concerns["namespace"], rule.concerns["podLabels"]
            )
            if rule_host not in isolated_hosts:
                isolated_hosts.append(rule_host)
            if rule.allowed:  # means it is NOT default deny rule
                for connection in rule.allowed:
                    for port in connection.ports:
                        on_port = port
                        other_host = _get_other_host_from(
                            connection.targets, rule.concerns["namespace"]
                        )
                        other_hosts.append(other_host)
                        if connection.direction == "to":
                            case = NetworkTestCase(rule_host, other_host, on_port, True)
                            outgoing_test_cases.append(case)
                        elif connection.direction == "from":
                            case = NetworkTestCase(other_host, rule_host, on_port, True)
                            incoming_test_cases.append(case)
                        else:
                            raise ValueError(
                                "Direction '%s' unknown!" % connection.direction
                            )
        positive_test_time = time.time()
        runtimes["positiveTestGen"] = positive_test_time - net_pol_parsing_time
        (
            negative_test_cases,
            negative_test_gen_runtimes,
        ) = self.generate_negative_cases_for_incoming_cases(
            isolated_hosts, incoming_test_cases, other_hosts, namespaces
        )
        runtimes["negativeTestGen"] = negative_test_gen_runtimes
        return outgoing_test_cases + negative_test_cases + incoming_test_cases, runtimes

    # TODO: implement it also for outgoing test cases
    # TODO: divide this into submethods
    def generate_negative_cases_for_incoming_cases(
        self, isolated_hosts, incoming_test_cases, other_hosts, namespaces
    ):
        """
        Generates negative test cases based on desired positive test cases
        """
        runtimes = {}
        start_time = time.time()
        # list of all namespace labels set on other hosts
        namespace_labels = [
            h.namespace_labels for h in other_hosts if isinstance(h, GenericClusterHost)
        ]
        namespaces_per_label_strings = get_namespace_label_strings(
            namespace_labels, namespaces
        )
        namespace_label_resolve_time = time.time()
        runtimes["nsLabelResolve"] = namespace_label_resolve_time - start_time
        labels_per_namespace = {n.metadata.name: n.metadata.labels for n in namespaces}
        overlaps_per_host = {
            host: self.get_overlapping_hosts(
                host,
                namespaces_per_label_strings,
                labels_per_namespace,
                isolated_hosts + other_hosts,
            )
            for host in isolated_hosts
        }
        overlap_calc_time = time.time()
        runtimes["overlapCalc"] = overlap_calc_time - namespace_label_resolve_time
        cases = []
        for host in isolated_hosts:
            host_string = str(host)
            host_start_time = time.time()
            runtimes[host_string] = {}
            # Check for hosts that can target these to construct negative cases from
            self.logger.debug(overlaps_per_host[host])
            allowed_hosts_with_ports = [
                (test_case.from_host, test_case.port_string)
                for test_case in incoming_test_cases
                if test_case.to_host in overlaps_per_host[host]
            ]
            self.logger.debug("allowed_hosts_with_ports=%s", allowed_hosts_with_ports)
            reaching_host_find_time = time.time()
            runtimes[host_string]["findReachingHosts"] = (
                reaching_host_find_time - host_start_time
            )
            if allowed_hosts_with_ports:
                allowed_hosts, _ = zip(*allowed_hosts_with_ports)
                ports_per_host = {
                    host: [
                        port
                        for _host, port in allowed_hosts_with_ports
                        if _host == host
                    ]
                    for host in allowed_hosts
                }
                match_all_host = GenericClusterHost({}, {})
                if match_all_host in allowed_hosts:
                    # All hosts are allowed to reach (on some ports or all) => results from ALLOW all
                    if "*" in ports_per_host[match_all_host]:
                        self.logger.info(
                            "Not generating negative tests for host %s"
                            "as all connections to it are allowed",
                            host,
                        )
                    else:
                        cases.append(
                            NetworkTestCase(
                                match_all_host,
                                host,
                                rand_port(ports_per_host[match_all_host]),
                                False,
                            )
                        )
                    runtimes[host_string]["matchAllCase"] = (
                        time.time() - reaching_host_find_time
                    )
                else:
                    inverted_hosts = set(
                        [
                            h
                            for l in [invert_host(host) for host in allowed_hosts]
                            for h in l
                        ]
                    )
                    hosts_on_inverted = {
                        h: originalHost
                        for l, originalHost in [
                            (invert_host(host), host) for host in allowed_hosts
                        ]
                        for h in l
                    }
                    host_inversion_time = time.time()
                    runtimes[host_string]["hostInversion"] = (
                        host_inversion_time - reaching_host_find_time
                    )
                    overlaps_for_inverted_hosts = {
                        h: self.get_overlapping_hosts(
                            h,
                            namespaces_per_label_strings,
                            labels_per_namespace,
                            allowed_hosts,
                        )
                        for h in inverted_hosts
                    }
                    overlap_calc_time = time.time()
                    runtimes[host_string]["overlapCalc"] = (
                        overlap_calc_time - host_inversion_time
                    )
                    self.logger.debug("InvertedHosts: %s", inverted_hosts)
                    negative_test_targets = [
                        h
                        for h in inverted_hosts
                        if len(overlaps_for_inverted_hosts[h]) <= 1
                    ]
                    self.logger.debug("NegativeTestTargets: %s", negative_test_targets)
                    # now remove the inverted hosts that are reachable
                    for target in negative_test_targets:
                        ports_for_inverted_hosts_original_host = ports_per_host[
                            hosts_on_inverted[target]
                        ]
                        if ports_for_inverted_hosts_original_host:
                            cases.append(
                                NetworkTestCase(
                                    target,
                                    host,
                                    ports_for_inverted_hosts_original_host[0],
                                    False,
                                )
                            )
                        else:
                            cases.append(NetworkTestCase(target, host, "*", False))
                    runtimes[host_string]["casesGen"] = time.time() - overlap_calc_time
            else:
                # No hosts are allowed to reach host -> it should be totally isolated
                # => results from default deny policy
                cases.append(NetworkTestCase(host, host, "*", False))
            runtimes["all"] = time.time() - start_time
        return cases, runtimes

    def get_overlapping_hosts(
        self, host, namespaces_per_label_strings, labels_per_namespace, other_hosts
    ):
        """
        Returns a list of hosts that might be selected by the same policies
        """
        out = [host]
        for other in other_hosts:
            if host is not other:
                namespace_overlap = self.namespaces_overlap(
                    host, namespaces_per_label_strings, labels_per_namespace, other
                )
                pod_label_overlap = label_selector_overlap(
                    other.pod_labels, host.pod_labels
                )
                if namespace_overlap and pod_label_overlap:
                    out.append(other)
        return out

    def namespaces_overlap(
        self, host, namespaces_per_label_strings, labels_per_namespace, other_host
    ):
        """
        Checks whether two hosts have namespaces in common
        """
        host_ns = self.resolve_namespaces(host, namespaces_per_label_strings)
        other_ns = self.resolve_namespaces(other_host, namespaces_per_label_strings)
        if host_ns and other_ns:
            return any(ns in other_ns for ns in host_ns)
        ns_labels = lookup_namespace_labels(host, labels_per_namespace)
        other_ns_labels = lookup_namespace_labels(other_host, labels_per_namespace)
        if ns_labels is not None and other_ns_labels is not None:
            return label_selector_overlap(ns_labels, other_ns_labels)
        return False

    def resolve_namespaces(self, host, namespaces_per_label_strings):
        """
        Returns the namespace of a given host
        """
        self.logger.debug(host)
        if isinstance(host, ClusterHost):
            return [host.namespace]

        labels = labels_to_string(host.namespace_labels)
        return (
            namespaces_per_label_strings[labels]
            if labels in namespaces_per_label_strings
            else []
        )


def invert_host(host):
    """
    Returns a list of either inverted GenericClusterHosts or inverted ClusterHosts
    """
    if isinstance(host, GenericClusterHost):
        return invert_generic_cluster_host(host)
    if isinstance(host, ClusterHost):
        return invert_cluster_host(host)
    raise ValueError("Host %s is of unsupported type" % host)


def invert_cluster_host(host: ClusterHost):
    """
    Returns a list of ClusterHosts with
    once inverted pod label selectors,
    once inverted namespace label selectors
    and once both
    """
    if host.pod_labels == {}:
        return [ClusterHost("%s%s" % (INVERTED_ATTRIBUTE_PREFIX, host.namespace), {})]

    inverted_hosts = [
        ClusterHost(
            "%s%s" % (INVERTED_ATTRIBUTE_PREFIX, host.namespace), host.pod_labels
        ),
        ClusterHost(
            "%s%s" % (INVERTED_ATTRIBUTE_PREFIX, host.namespace),
            invert_label_selector(host.pod_labels),
        ),
        ClusterHost(host.namespace, invert_label_selector(host.pod_labels)),
    ]
    return inverted_hosts


def invert_generic_cluster_host(host: GenericClusterHost):
    """
    Returns a list of GenericClusterHosts with
    once inverted pod label selectors,
    once inverted namespace label selectors
    and once both
    """
    if host == GenericClusterHost({}, {}):
        raise ValueError(
            "Cannot invert GenericClusterHost matching all hosts in cluster"
        )
    if host.namespace_labels == {}:
        return [GenericClusterHost({}, invert_label_selector(host.pod_labels))]
    inverted_hosts = [
        GenericClusterHost(
            host.namespace_labels, invert_label_selector(host.pod_labels)
        ),
        GenericClusterHost(
            invert_label_selector(host.namespace_labels), host.pod_labels
        ),
        GenericClusterHost(
            invert_label_selector(host.namespace_labels),
            invert_label_selector(host.pod_labels),
        ),
    ]
    return inverted_hosts


def invert_label_selector(labels):
    """
    Inverts a label selector
    """
    return {"%s%s" % (INVERTED_ATTRIBUTE_PREFIX, k): v for k, v in labels.items()}


def label_selector_overlap(label_selector_1, label_selector_2):
    """
    Returns the intersection of two label selectors
    """
    if label_selector_1 and label_selector_2:
        return any(
            item in label_selector_2.items() for item in label_selector_1.items()
        )
    # if one of the label selector dicts is empty, they always overlap, as empty label selectors select all labels
    return True


def lookup_namespace_labels(host, labels_per_namespace):
    """
    Returns the namespace labels of a host
    """
    if isinstance(host, GenericClusterHost):
        return host.namespace_labels

    if host.namespace in labels_per_namespace:
        return labels_per_namespace[host.namespace]

    return None
