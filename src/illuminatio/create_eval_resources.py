import click
import kubernetes as k8s
import time
from illuminatio.util import ROLE_LABEL, CLEANUP_LABEL, CLEANUP_ALWAYS, get_target_image

NAME_PREFIX = "illuminatio-"


@click.command()
@click.option('--netpolcount')
@click.option('--resourcecount')
@click.option('--incluster', default=False, is_flag=True)
def cli(netpolcount, resourcecount, incluster):
    if not resourcecount:
        raise ValueError("resourcecount must be set")
    if not netpolcount:
        raise ValueError("netpolcount must be set")
    resourcecount = int(resourcecount)
    netpolcount = int(netpolcount)
    if resourcecount > netpolcount:
        raise ValueError("resourcecount cannot be higher than netpol count")
    if netpolcount <= 0:
        click.echo("No resources created, as netpolcount was <= 0")
        return
    if incluster:
        k8s.config.load_incluster_config()
    else:
        k8s.config.load_kube_config()
    core_api = k8s.client.CoreV1Api()
    net_api = k8s.client.NetworkingV1Api()
    namespace_name = NAME_PREFIX + "ns"
    namespace_labels = {ROLE_LABEL: "eval_namespace", CLEANUP_LABEL: CLEANUP_ALWAYS}
    resp = core_api.create_namespace(
        k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name=namespace_name, labels=namespace_labels)))
    if not isinstance(resp, k8s.client.V1Namespace):
        raise Exception("Could not create namespace for evaluation")
    start = time.time()
    click.echo(
        "Creating " + str(netpolcount) + " networkpolicies as well as " + str(resourcecount) + " pods and services.")
    with click.progressbar(range(1, netpolcount + 1)) as progress_bar:
        for netpol_num in progress_bar:
            ingress_pod_labels = {NAME_PREFIX + "num": str(netpol_num)}
            name = NAME_PREFIX + str(netpol_num)
            net_pol = k8s.client.V1NetworkPolicy(metadata=k8s.client.V1ObjectMeta(name=name, namespace=namespace_name,
                                                                                  labels={
                                                                                      CLEANUP_LABEL: CLEANUP_ALWAYS}))
            net_pol.spec = k8s.client.V1NetworkPolicySpec(ingress=[k8s.client.V1NetworkPolicyIngressRule()],
                                                          pod_selector=k8s.client.V1LabelSelector(
                                                              match_labels=ingress_pod_labels))
            net_api.create_namespaced_network_policy(namespace_name, net_pol)
            if resourcecount > netpol_num:
                # prepare pod that is chosen by ingress and spec.labels of the netpol in its namespace
                pod_labels = {CLEANUP_LABEL: CLEANUP_ALWAYS, ROLE_LABEL: "eval_pod"}
                pod_labels.update(ingress_pod_labels)
                pod = k8s.client.V1Pod(
                    metadata=k8s.client.V1ObjectMeta(name=name, labels=pod_labels, namespace=namespace_name))
                pod.spec = k8s.client.V1PodSpec(
                    containers=[k8s.client.V1Container(image=get_target_image(), name="runner")])
                # prepare service for pod
                svc_labels = {CLEANUP_LABEL: CLEANUP_ALWAYS, ROLE_LABEL: "eval_svc"}
                svc = k8s.client.V1Service(
                    metadata=k8s.client.V1ObjectMeta(name=name, labels=svc_labels, namespace=namespace_name))
                svc.spec = k8s.client.V1ServiceSpec(selector=ingress_pod_labels,
                                                    ports=[k8s.client.V1ServicePort(port=80)])
                # create them
                try:
                    core_api.create_namespaced_pod(namespace_name, pod)
                except k8s.client.rest.ApiException:
                    click.echo("ServiceAccount default for namespace " + str(
                        namespace_name) + " was missing, waiting for creation before retry")
                    while not core_api.list_namespaced_service_account(namespace_name,
                                                                       field_selector="metadata.name=default").items:
                        time.sleep(2)
                    click.echo("ServiceAccount default for namespace " + str(
                        namespace_name) + " exists, retrying pod creation now")
                    core_api.create_namespaced_pod(namespace_name, pod)
                core_api.create_namespaced_service(namespace_name, svc)
    click.echo("Created " + str(netpolcount) + " networkpolicies and " + str(
        resourcecount) + " pods and services in " + "{:.0f}".format(time.time() - start) + "s")
