"""
File for all kinds of hosts on which network tests can be performed
"""
from abc import ABC

import kubernetes as k8s


class Host(ABC):
    """
    Class for all kinds of hosts on which network tests can be performed
    """
    def to_identifier(self):
        """
        Abstract function returning the host identifier
        """
        return self

    def matches(self, obj):
        """
        Compares the Host with a given object
        """
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        return self == obj

    @classmethod
    def from_identifier(cls, identifier: str):
        """
        Returns the host type of a given identifier.
        """
        if identifier == LocalHost().to_identifier():
            return LocalHost()
        if '.' in identifier:
            return ExternalHost(identifier)
        split_namespace = identifier.split(":")
        pod_label_string = (split_namespace[1] if len(split_namespace) > 1 else split_namespace[0])
        labels = Host._labels_from_string(pod_label_string)
        namespace = split_namespace[0] if len(split_namespace) > 1 else "default"
        if "=" in namespace or "*" in namespace:
            return GenericClusterHost(Host._labels_from_string(namespace), labels)
        if labels is not None:
            return ClusterHost(namespace, labels)
        return ConcreteClusterHost(namespace, pod_label_string)

    @staticmethod
    def _labels_from_string(label_string):
        if label_string == "*":
            return {}
        if "=" in label_string:
            split_labels = label_string.split(",")
            labels = {sp.split("=")[0]: sp.split("=")[1] for sp in split_labels}
            return labels
        return None


class ConcreteClusterHost(Host):
    """
    Concrete class for cluster hosts
    """
    def __init__(self, namespace, name):
        if namespace is None:
            raise ValueError("namespace may not be None")
        if name is None:
            raise ValueError("name may not be None")
        self.namespace = namespace
        self.name = name

    def __eq__(self, other):
        if isinstance(other, ConcreteClusterHost):
            return (self.namespace == other.namespace
                    and self.name == other.name)
        return False

    def __hash__(self):
        return hash(str(self))

    def to_identifier(self):
        return "%s:%s" % (str(self.namespace), str(self.name))

    def __str__(self):
        return "ConcreteClusterHost(namespace=%s, name=%s)" % (str(self.namespace), str(self.name))

    def __repr__(self):
        return self.__str__()


class ClusterHost(Host):
    """
    Class for cluster hosts
    """
    def __init__(self, namespace, pod_labels):
        if namespace is None:
            raise ValueError("namespace may not be None")
        if pod_labels is None:
            raise ValueError("podLabels may not be None")
        self.namespace = namespace
        self.pod_labels = pod_labels

    def __eq__(self, other):
        if isinstance(other, ClusterHost):
            return (self.namespace == other.namespace
                    and self.pod_labels == other.pod_labels)
        return False

    def __hash__(self):
        return hash(str(self))

    def to_identifier(self):
        return "%s:%s" % (str(self.namespace), ("*" if not self.pod_labels else
                                                ",".join(["%s=%s" % (str(k).strip(), str(v).strip())
                                                          for k, v in self.pod_labels.items()])))

    def matches(self, obj):
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        if isinstance(obj, k8s.client.V1Pod):
            return (obj.metadata.namespace == self.namespace
                    and obj.metadata.labels is not None
                    and all(item in obj.metadata.labels.items() for item in self.pod_labels.items()))
        if isinstance(obj, k8s.client.V1Service):
            return (obj.metadata.namespace == self.namespace
                    and obj.spec.selector is not None
                    and all(item in obj.spec.selector.items() for item in self.pod_labels.items()))
        if isinstance(obj, k8s.client.V1Namespace):
            return obj.metadata.name == self.namespace
        raise ValueError("Cannot match object of type %s" % type(obj))

    def __str__(self):
        return "ClusterHost(namespace=%s, podLabels=%s)" % (str(self.namespace), str(self.pod_labels))

    def __repr__(self):
        return self.__str__()


class GenericClusterHost(Host):
    """
    Abstract class for cluster hosts,
    can be used to express multiple hosts e.g. with different namespace labels
    """
    def __init__(self, namespace_labels, pod_labels):
        if namespace_labels is None:
            raise ValueError("namespaceLabels may not be None")
        if pod_labels is None:
            raise ValueError("podLabels may not be None")
        self.namespace_labels = namespace_labels
        self.pod_labels = pod_labels

    def __eq__(self, other):
        if isinstance(other, GenericClusterHost):
            return (self.namespace_labels == other.namespace_labels
                    and self.pod_labels == other.pod_labels)
        return False

    def __hash__(self):
        return hash(str(self))

    def matches(self, obj):
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        if isinstance(obj, k8s.client.V1Namespace):
            return (obj.metadata.labels is not None
                    and all(item in obj.metadata.labels.items() for item in self.namespace_labels.items()))
        # we need to request the namespace from the cluster to match the labels TODO: find better solution
        namespace = k8s.client.CoreV1Api().read_namespace(obj.metadata.namespace)
        namespace_matches = (namespace.metadata.labels is not None and
                             all(item in namespace.metadata.labels.items() for item in
                                 self.namespace_labels.items()))
        if isinstance(obj, k8s.client.V1Pod):
            return (namespace_matches and obj.metadata.labels is not None
                    and all(item in obj.metadata.labels.items() for item in self.pod_labels.items()))
        if isinstance(obj, k8s.client.V1Service):
            return (namespace_matches and obj.spec.selector is not None
                    and all(item in obj.spec.selector.items() for item in self.pod_labels.items()))
        raise TypeError("obj is neither a pod nor a service")

    def to_identifier(self):
        return ("%s:%s" % (("*" if not self.namespace_labels else ",".join(
            ["%s=%s" % (str(k).strip(), str(v).strip()) for k, v in self.namespace_labels.items()])),
                           ("*" if not self.pod_labels else ",".join(["%s=%s" % (str(k).strip(), str(v).strip())
                                                                      for k, v in self.pod_labels.items()]))))

    def __str__(self):
        return "GenericClusterHost(namespaceLabels=%s, podLabels=%s)" % (
            str(self.namespace_labels), str(self.pod_labels))

    def __repr__(self):
        return self.__str__()


class ExternalHost(Host):
    """
    Class for execution on an external host
    """
    def __init__(self, ip_address):
        self.ip_address = ip_address

    def __str__(self):
        return "ExternalHost(ipAddress=%s)" % str(self.ip_address)

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, ExternalHost):
            return False
        return self.ip_address == other.ip_address

    def to_identifier(self):
        return str(self.ip_address)


class LocalHost(Host):
    """
    Class for execution on localhost
    """
    def __str__(self):
        return "LocalHost()"

    def __eq__(self, other):
        return isinstance(other, LocalHost)

    def __repr__(self):
        return self.__str__()

    def to_identifier(self):
        return "localhost"
