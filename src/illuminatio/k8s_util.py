import kubernetes as k8s
from illuminatio.host import Host
from illuminatio.util import CLEANUP_LABEL, validate_cleanup_in, CLEANUP_ON_REQUEST, CLEANUP_ALWAYS, ROLE_LABEL


def init_service_account_for_runners(name, namespace):
    sa_labels = {CLEANUP_LABEL: CLEANUP_ON_REQUEST, ROLE_LABEL: "runner-service-account"}
    sa_meta = k8s.client.V1ObjectMeta(name=name, namespace=namespace, labels=sa_labels)
    return k8s.client.V1ServiceAccount(metadata=sa_meta)


def init_role_binding_for_service_account(namespace, name, sa_name):
    # role binding for account, granting it admin rights for the moment (TODO limit rights)
    rb_labels = {CLEANUP_LABEL: CLEANUP_ON_REQUEST, ROLE_LABEL: "runner-rb"}
    rb_meta = k8s.client.V1ObjectMeta(name=name, labels=rb_labels)
    role_ref = k8s.client.V1RoleRef(name="illuminatio", api_group="rbac.authorization.k8s.io", kind="ClusterRole")
    rb_subject = k8s.client.V1Subject(namespace=namespace, name=sa_name, kind="ServiceAccount")
    return k8s.client.V1ClusterRoleBinding(metadata=rb_meta, role_ref=role_ref, subjects=[rb_subject])


def update_role_binding(role_binding: k8s.client.V1ClusterRoleBinding, namespaces, sa_name):
    existing_ns = [sub.namespace for sub in role_binding.subjects]
    rb_subjects = [k8s.client.V1Subject(namespace=ns, name=sa_name, kind="ServiceAccount") for ns in namespaces if
                   ns not in existing_ns]
    role_binding.subjects.extend(rb_subjects)
    return role_binding


def init_test_output_config_map(namespace, name, data=None):
    meta = k8s.client.V1ObjectMeta(namespace=namespace, name=name, labels={CLEANUP_LABEL: CLEANUP_ALWAYS})
    cfg_map = k8s.client.V1ConfigMap(metadata=meta)
    cfg_map.data = {"results": data}
    return cfg_map


def init_pod(host: Host, additional_labels, generate_name, container, sa_name="default"):
    pod = k8s.client.V1Pod()
    labels = {k: v for k, v in host.pod_labels.items()}
    for k, v in additional_labels.items():
        labels[k] = v
    validate_cleanup_in(labels)
    pod.metadata = k8s.client.V1ObjectMeta(generate_name=generate_name,
                                           namespace=host.namespace,
                                           labels=labels)
    pod.spec = k8s.client.V1PodSpec(containers=[container], service_account_name=sa_name)
    return pod


def init_svc(host: Host, additional_selector_labels, svc_labels, name, port_nums):
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
    return ",".join([str(k) + "=" + str(v) for k, v in labels.items()]) if labels else "*"
