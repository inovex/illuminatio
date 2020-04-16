"""
File for the creation of networking rules
"""
from collections import namedtuple
import kubernetes as k8s

# identifiers:
POD_SELECTOR_LABELS = "podLabels"
NAMESPACE_SELECTOR_LABELS = "namespaceLabels"
NAMESPACE = "namespace"
DIRECTION_INCOMING = "from"
DIRECTION_OUTGOING = "to"
IP_BLOCK_EXCEPT = "except"
IP_BLOCK_CIDR = "cidr"
MATCH_ALL_WILDCARD = "*"

AFFECTED_POD_IDENTIFIER = "concerns"

# helper structs:
Conn = namedtuple("Connection", ["direction", "targets", "ports"])


def dict_mapper(obj):
    """
    Converts an object to a dictionary if possible
    """
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


class Connection(Conn):
    """
    Class for interaction with Connection tuples
    """

    def to_dict(self) -> dict:
        """
        converts a Connection tuple into a dictionary
        """
        return {
            self.direction: {
                "hosts": dict_mapper(self.targets),
                "ports": list(map(dict_mapper, self.ports)),
            }
        }


# main class
class Rule:
    """
    Class for networking rules
    """

    def __init__(self, concerns, allowed=None):
        if allowed is None:
            allowed = []
        self.concerns = concerns
        self.allowed = allowed

    def __str__(self):

        return "".join(
            [
                "Rule( ",
                AFFECTED_POD_IDENTIFIER,
                "= ",
                str(self.concerns),
                ", allowed= ",
                str(self.allowed),
            ]
        )

    def __repr__(self):
        return self.__str__()

    def to_dict(self) -> dict:
        """
        Converts a rule into a dictionary
        """
        return {
            AFFECTED_POD_IDENTIFIER: self.concerns,
            "allowed": list(map(dict_mapper, self.allowed)),
        }

    @classmethod
    def from_network_policy(cls, net_pol: k8s.client.V1NetworkPolicy):
        """
        Returns a class containing the concerns and rules of a given NetworkPolicy
        """
        concerns = {NAMESPACE: net_pol.metadata.namespace}
        if net_pol.spec.pod_selector.match_labels is not None:
            concerns[POD_SELECTOR_LABELS] = net_pol.spec.pod_selector.match_labels
        else:
            concerns[POD_SELECTOR_LABELS] = {}
        # evaluate network policy for rules
        allowed = []
        if net_pol.spec.ingress is not None:
            for ing in net_pol.spec.ingress:
                allowed.extend(
                    build_connections(DIRECTION_INCOMING, ing._from, ing.ports)
                )
        if net_pol.spec.egress is not None:
            for egr in net_pol.spec.egress:
                allowed.extend(build_connections(DIRECTION_OUTGOING, egr.to, egr.ports))
        # return as object
        return cls(concerns, allowed)


# helper function
def build_connections(verb, target, ports):
    """
    Helper function to build Connection tuples
    """
    out = []
    port_list = [p.port for p in ports] if (ports is not None) else [MATCH_ALL_WILDCARD]
    if target is not None:
        for item in target:
            if item.ip_block is not None:
                ip_block_dict = {}
                if item.ip_block._except is not None:
                    ip_block_dict[IP_BLOCK_EXCEPT] = item.ip_block._except
                if item.ip_block.cidr is not None:
                    ip_block_dict[IP_BLOCK_CIDR] = item.ip_block.cidr
                # TODO: reenable this, if external pods are ever to be tested
                # out.append(Connection(verb, ip_block_dict, port_list))
            # handle namespace AND pod selector separately to individuals
            elif item.namespace_selector is not None and item.pod_selector is not None:
                selector_dict = _extract_name_space_selector_from(item)
                for key, value in _extract_pod_selector_from(item).items():
                    selector_dict[key] = value
                out.append(Connection(verb, selector_dict, port_list))
            elif item.namespace_selector is not None:
                out.append(
                    Connection(verb, _extract_name_space_selector_from(item), port_list)
                )
            elif item.pod_selector is not None:
                out.append(
                    Connection(verb, _extract_pod_selector_from(item), port_list)
                )
    else:
        out.append(Connection(verb, {}, port_list))
    return out


def _extract_name_space_selector_from(item):
    if (
        item.namespace_selector.match_labels is not None
        and item.namespace_selector.match_expressions is None
    ):
        return {NAMESPACE_SELECTOR_LABELS: item.namespace_selector.match_labels}
    if (
        item.namespace_selector.match_labels is None
        and item.namespace_selector.match_expressions is not None
    ):
        raise ValueError(
            "match_expressions in namespace_selector currently unsupported"
        )
    return {NAMESPACE_SELECTOR_LABELS: {}}


def _extract_pod_selector_from(item):
    if (
        item.pod_selector.match_labels is not None
        and item.pod_selector.match_expressions is None
    ):
        return {POD_SELECTOR_LABELS: item.pod_selector.match_labels}
    if (
        item.pod_selector.match_labels is None
        and item.pod_selector.match_expressions is not None
    ):
        raise ValueError("match_expressions in pod_selector currently unsupported")
    return {POD_SELECTOR_LABELS: {}}
