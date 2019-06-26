from typing import List
import yaml
from illuminatio.host import Host


class NetworkTestCase:
    """ Class that encompasses a single network test case. """

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
        self.port_string = ("" if self._should_connect else "-") + str(self._on_port)

    def __eq__(self, other):
        if isinstance(other, NetworkTestCase):
            return (self.from_host == other.from_host
                    and self.to_host == other.to_host
                    and self.port_string == other.port_string)
        return False

    def __str__(self):
        return ("NetworkTestCase(from=" + str(self.from_host) + ", to=" + str(self.to_host) +
                ", port=" + self.port_string + ")")

    def __repr__(self):
        return self.__str__()

    def matches(self, objs):
        return self.from_host_matches_any(objs) and self.to_host_matches_any(objs)

    def from_host_matches_any(self, objs):
        return any([self.from_host.matches(obj) for obj in objs])

    def to_host_matches_any(self, objs):
        return any([self.to_host.matches(obj) for obj in objs])

    def stringify_members(self):
        return self.from_host.to_identifier(), self.to_host.to_identifier(), self.port_string

    @classmethod
    def from_stringified_members(cls, from_host_string, to_host_string, port_string):
        from_host = Host.from_identifier(from_host_string)
        to_host = Host.from_identifier(to_host_string)
        if "-" not in port_string:
            return NetworkTestCase(from_host, to_host, port_string, True)
        return NetworkTestCase(from_host, to_host, port_string[1:], False)


def merge_in_dict(cases: List[NetworkTestCase]):
    out = {}
    for fromHost, toHost, port in [case.stringify_members() for case in cases]:
        if fromHost in out.keys():
            if toHost in out[fromHost].keys():
                out[fromHost][toHost].append(port)
            else:
                out[fromHost][toHost] = [port]
        else:
            out[fromHost] = {toHost: [port]}
    return out


def to_yaml(cases: List[NetworkTestCase]):
    return yaml.dump(merge_in_dict(cases))


def triples_from_dict(yaml_dict: dict):
    out = []
    for from_key in yaml_dict.keys():
        for to_key in yaml_dict[from_key].keys():
            for port in yaml_dict[from_key][to_key]:
                out.append((from_key, to_key, port))
    return out


def from_yaml(yaml_string) -> List[NetworkTestCase]:
    return [NetworkTestCase.from_stringified_members(f, t, p)
            for f, t, p in triples_from_dict(yaml.safe_load(yaml_string))]
