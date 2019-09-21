"""
File with several useful functions for interacting with k8s
"""

import kubernetes as k8s
from illuminatio.host import Host
from illuminatio.util import CLEANUP_LABEL, validate_cleanup_in, CLEANUP_ON_REQUEST, CLEANUP_ALWAYS, ROLE_LABEL


def create_service_account_manifest_for_runners(name, namespace):
    """
    Creates and returns a ServiceAccount manifest for the illuminatio runner
    """
    sa_labels = {CLEANUP_LABEL: CLEANUP_ON_REQUEST, ROLE_LABEL: "runner-service-account"}
    sa_meta = k8s.client.V1ObjectMeta(name=name, namespace=namespace, labels=sa_labels)
    return k8s.client.V1ServiceAccount(metadata=sa_meta)


def create_role_binding_manifest_for_service_account(namespace, name, sa_name):
    """
    Creates and returns a ClusterRoleBinding manifest for the illuminatio service account
    """
    rb_labels = {CLEANUP_LABEL: CLEANUP_ON_REQUEST, ROLE_LABEL: "runner-rb"}
    rb_meta = k8s.client.V1ObjectMeta(name=name, labels=rb_labels)
    role_ref = k8s.client.V1RoleRef(name="illuminatio", api_group="rbac.authorization.k8s.io", kind="ClusterRole")
    rb_subject = k8s.client.V1Subject(namespace=namespace, name=sa_name, kind="ServiceAccount")
    return k8s.client.V1ClusterRoleBinding(metadata=rb_meta, role_ref=role_ref, subjects=[rb_subject])


def update_role_binding_manifest(role_binding: k8s.client.V1ClusterRoleBinding, namespaces, sa_name):
    """
    Updates a ClusterRoleBinding manifest and returns it
    """
    existing_ns = [sub.namespace for sub in role_binding.subjects]
    rb_subjects = [k8s.client.V1Subject(namespace=ns, name=sa_name, kind="ServiceAccount") for ns in namespaces if
                   ns not in existing_ns]
    role_binding.subjects.extend(rb_subjects)
    return role_binding


def create_test_output_config_map_manifest(namespace, name, data=None):
    """
    Creates and returns a ConfigMap manifest with given parameters
    """
    meta = k8s.client.V1ObjectMeta(namespace=namespace, name=name, labels={CLEANUP_LABEL: CLEANUP_ALWAYS})
    cfg_map = k8s.client.V1ConfigMap(metadata=meta)
    cfg_map.data = {"results": data}
    return cfg_map


def create_pod_manifest(host: Host, additional_labels, generate_name, container):
    """
    Creates a pod manifest with given parameters
    """
    pod = k8s.client.V1Pod()
    labels = {key: value for key, value in host.pod_labels.items()}
    for key, value in additional_labels.items():
        labels[key] = value
    validate_cleanup_in(labels)
    pod.metadata = k8s.client.V1ObjectMeta(generate_name=generate_name,
                                           namespace=host.namespace,
                                           labels=labels)
    pod.spec = k8s.client.V1PodSpec(containers=[container], automount_service_account_token=False)
    return pod


def create_service_manifest(host: Host, additional_selector_labels, svc_labels, name, port_nums):
    """
    Creates and returns a service manifest with given parameters
    """
    svc_meta = k8s.client.V1ObjectMeta(name=name, namespace=host.namespace)
    svc = k8s.client.V1Service(api_version="v1", kind="Service", metadata=svc_meta)
    svc.spec = k8s.client.V1ServiceSpec()
    svc.spec.selector = {k: v for k, v in host.pod_labels.items()}
    for key, value in additional_selector_labels.items():
        svc.spec.selector[key] = value
    svc.metadata.labels = svc_labels
    validate_cleanup_in(svc.metadata.labels)
    # TODO: support for other protocols missing, target port might not work like that for multiple ports
    ports = [k8s.client.V1ServicePort(protocol="TCP", port=portNum, target_port=80) for portNum in port_nums]
    svc.spec.ports = ports
    return svc


def labels_to_string(labels):
    """
    Concatenates a list of labels to a single string to match the labelselector pattern
    """
    return ",".join(["%s=%s" % (str(k), str(v)) for k, v in labels.items()]) if labels else "*"
