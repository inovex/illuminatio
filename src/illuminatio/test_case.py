"""
File containing utilities for NetworkTestCases
"""
from typing import List
import yaml
from illuminatio.host import Host


class NetworkTestCase:
    """
    Class that describes a single network test case
    """

    def __init__(self, from_host: Host, to_host: Host, on_port, should_connect):
        if from_host is None:
            raise ValueError("fromHost may not be None")
        if to_host is None:
            raise ValueError("toHost may not be None")
        if on_port is None:
            raise ValueError("onPort may not be None")
        if should_connect is None:
            raise ValueError("shouldConnect may not be None")
        self.from_host = from_host
        self.to_host = to_host
        self._on_port = on_port
        self._should_connect = should_connect
        self.port_string = "%s%s" % (("" if self._should_connect else "-"), str(self._on_port))

    def __eq__(self, other):
        if isinstance(other, NetworkTestCase):
            return (self.from_host == other.from_host
                    and self.to_host == other.to_host
                    and self.port_string == other.port_string)
        return False

    def __str__(self):
        return "NetworkTestCase(from=%s, to=%s, port=%s)" % (
            str(self.from_host), str(self.to_host), self.port_string)

    def __repr__(self):
        return self.__str__()

    def matches(self, pods):
        """
        Checks whether both sender and target pod are contained in a given list
        """
        return self.from_host_matches_any(pods) and self.to_host_matches_any(pods)

    def from_host_matches_any(self, pods):
        """
        Checks whether a list contains the sender pod
        """
        return any([self.from_host.matches(pod) for pod in pods])

    def to_host_matches_any(self, pods):
        """
        Checks whether a list contains the target pod
        """
        return any([self.to_host.matches(pod) for pod in pods])

    def stringify_members(self):
        """
        Returns the stringified components of a NetworkTestCase
        """
        return self.from_host.to_identifier(), self.to_host.to_identifier(), self.port_string

    def __lt__(self, other):
        if isinstance(other, NetworkTestCase):
            return str(self) < str(other)
        raise TypeError("'<' not supported between instances of 'NetworkTestCase' and %s" % type(other))

    @classmethod
    def from_stringified_members(cls, sender_pod_string, target_pod_string, port_string):
        """
        Creates a NetworkTestCase affecting the connectability from one pod to another on a specific port
        """
        sender_pod = Host.from_identifier(sender_pod_string)
        target_pod = Host.from_identifier(target_pod_string)
        if "-" not in port_string:
            return NetworkTestCase(sender_pod, target_pod, port_string, True)
        return NetworkTestCase(sender_pod, target_pod, port_string[1:], False)


def merge_in_dict(cases: List[NetworkTestCase]):
    """
    Converts a list of NetworkTestCases into a dictionary
    """
    out = {}
    for from_host, to_host, port in [case.stringify_members() for case in cases]:
        if from_host in out.keys():
            if to_host in out[from_host].keys():
                out[from_host][to_host].append(port)
            else:
                out[from_host][to_host] = [port]
        else:
            out[from_host] = {to_host: [port]}
    return out


def to_yaml(cases: List[NetworkTestCase]):
    """
    Converts a list of NetworkTestCases into a yaml string
    """
    return yaml.dump(merge_in_dict(cases))


def triples_from_dict(dictionary: dict):
    """
    Converts a dictionary into a list of triples
    """
    out = []
    for from_key in dictionary.keys():
        for to_key in dictionary[from_key].keys():
            for port in dictionary[from_key][to_key]:
                out.append((from_key, to_key, port))
    return out


def from_yaml(yaml_string) -> List[NetworkTestCase]:
    """
    Converts a yaml string into a list of NetworkTestCases
    """
    return [NetworkTestCase.from_stringified_members(f, t, p)
            for f, t, p in triples_from_dict(yaml.safe_load(yaml_string))]
