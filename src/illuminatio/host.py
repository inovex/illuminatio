from abc import ABC

import kubernetes as k8s


class Host(ABC):

    def to_identifier(self):
        pass

    def matches(self, obj):
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        return False

    @classmethod
    def from_identifier(cls, identifier: str):
        if identifier == LocalHost().to_identifier():
            return LocalHost()
        elif '.' in identifier:
            return ExternalHost(identifier)
        else:
            split_ns = identifier.split(":")
            pod_label_string = (split_ns[1] if len(split_ns) > 1 else split_ns[0])
            labels = Host._labels_from_string(pod_label_string)
            ns = split_ns[0] if len(split_ns) > 1 else "default"
            if "=" in ns or "*" in ns:
                return GenericClusterHost(Host._labels_from_string(ns), labels)
            elif labels is not None:
                return ClusterHost(ns, labels)
            else:
                return ConcreteClusterHost(ns, pod_label_string)

    @staticmethod
    def _labels_from_string(label_string):
        if label_string == "*":
            return {}
        elif "=" in label_string:
            split_labels = label_string.split(",")
            labels = {sp.split("=")[0]: sp.split("=")[1] for sp in split_labels}
            return labels
        else:
            return None


class ConcreteClusterHost(Host):

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
        else:
            return False

    def __hash__(self):
        return hash(str(self))

    def to_identifier(self):
        return str(self.namespace) + ":" + str(self.name)

    def __str__(self):
        return "ConcreteClusterHost(namespace=" + str(self.namespace) + ", name=" + str(self.name) + ")"

    def __repr__(self):
        return self.__str__()


class ClusterHost(Host):

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
        else:
            return False

    def __hash__(self):
        return hash(str(self))

    def to_identifier(self):
        return (str(self.namespace) + ":" + ("*" if not self.pod_labels else
                                             ",".join([str(k).strip() + "=" + str(v).strip() for k, v in
                                                       self.pod_labels.items()])))

    def matches(self, obj):
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        else:
            if isinstance(obj, k8s.client.V1Pod):
                return (obj.metadata.namespace == self.namespace
                        and obj.metadata.labels is not None
                        and all(item in obj.metadata.labels.items() for item in self.pod_labels.items()))
            elif isinstance(obj, k8s.client.V1Service):
                return (obj.metadata.namespace == self.namespace
                        and obj.spec.selector is not None
                        and all(item in obj.spec.selector.items() for item in self.pod_labels.items()))
            elif isinstance(obj, k8s.client.V1Namespace):
                return obj.metadata.name == self.namespace
            else:
                raise ValueError("Cannot match object of type " + type(obj))

    def __str__(self):
        return "ClusterHost(namespace=" + str(self.namespace) + ", podLabels=" + str(self.pod_labels) + ")"

    def __repr__(self):
        return self.__str__()


class GenericClusterHost(Host):

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
        else:
            return False

    def __hash__(self):
        return hash(str(self))

    def matches(self, obj):
        if obj is None:
            raise ValueError("obj to match to cannot be None")
        elif isinstance(obj, k8s.client.V1Namespace):
            return (obj.metadata.labels is not None
                    and all(item in obj.metadata.labels.items() for item in self.namespace_labels.items()))
        else:
            # we need to request the namepsace from the cluster to match the labels TODO: find better solution
            namespace = \
                k8s.client.CoreV1Api().list_namespace(field_selector="metadata.name=" + obj.metadata.namespace).items[0]
            namespace_matches = (namespace.metadata.labels is not None and
                                 all(item in namespace.metadata.labels.items() for item in
                                     self.namespace_labels.items()))
            if isinstance(obj, k8s.client.V1Pod):
                return (namespace_matches and obj.metadata.labels is not None
                        and all(item in obj.metadata.labels.items() for item in self.pod_labels.items()))
            elif isinstance(obj, k8s.client.V1Service):
                return (namespace_matches and obj.spec.selector is not None
                        and all(item in obj.spec.selector.items() for item in self.pod_labels.items()))

    def to_identifier(self):
        return (("*" if not self.namespace_labels else ",".join(
            [str(k).strip() + "=" + str(v).strip() for k, v in self.namespace_labels.items()])) + ":" +
                ("*" if not self.pod_labels else ",".join(
                    [str(k).strip() + "=" + str(v).strip() for k, v in self.pod_labels.items()])))

    def __str__(self):
        return "GenericClusterHost(namespaceLabels=" + str(self.namespace_labels) + ", podLabels=" + str(
            self.pod_labels) + ")"

    def __repr__(self):
        return self.__str__()


class ExternalHost(Host):

    def __init__(self, ip_address):
        self.ip_address = ip_address

    def __str__(self):
        return "ExternalHost(ipAddress=" + str(self.ip_address) + ")"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, ExternalHost):
            return self.ip_address == other.ip_address
        else:
            return False

    def to_identifier(self):
        return str(self.ip_address)


class LocalHost(Host):

    def __str__(self):
        return "LocalHost()"

    def __eq__(self, other):
        return isinstance(other, LocalHost)

    def __repr__(self):
        return self.__str__()

    def to_identifier(self):
        return "localhost"
