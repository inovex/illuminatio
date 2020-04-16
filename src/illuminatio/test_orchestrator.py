"""
File containing all utilities to interact with test case related kubernetes resources
"""

import time
import json
from pkgutil import get_data
import yaml

import kubernetes as k8s
from illuminatio.host import ClusterHost, GenericClusterHost, Host
from illuminatio.k8s_util import (
    create_pod_manifest,
    create_role_binding_manifest_for_service_account,
    create_service_account_manifest_for_runners,
    create_service_manifest,
    labels_to_string,
    update_role_binding_manifest,
)
from illuminatio.test_case import merge_in_dict
from illuminatio.util import (
    PROJECT_NAMESPACE,
    PROJECT_PREFIX,
    CLEANUP_LABEL,
    ROLE_LABEL,
    CLEANUP_ALWAYS,
    CLEANUP_ON_REQUEST,
)
from illuminatio.util import rand_port


def get_container_runtime():
    """
    Fetches and retrieves the name of the container runtime used on kubernetes nodes
    """
    api = k8s.client.CoreV1Api()
    node_list = api.list_node()
    if node_list.items:
        container_runtime_name = node_list.items[
            0
        ].status.node_info.container_runtime_version
        for node in node_list.items:
            if (
                node.status.node_info.container_runtime_version
                != container_runtime_name
            ):
                raise ValueError(
                    "Different container runtime versions found on your nodes"
                )
        return container_runtime_name
    raise ValueError("Node not found")


def _hosts_are_in_cluster(case):
    return all(
        [
            isinstance(host, (ClusterHost, GenericClusterHost))
            for host in [case.from_host, case.to_host]
        ]
    )


class NetworkTestOrchestrator:
    """
    Class for handling test case related kubernetes resources
    """

    def __init__(self, test_cases, log):
        self.test_cases = test_cases
        self._current_pods = []
        self._current_services = []
        self.current_namespaces = []
        self.runner_daemon_set = None
        self.oci_images = {}
        self.logger = log

    def set_runner_image(self, runner_image):
        """
        Updates the runner docker image
        """
        self.oci_images["runner"] = runner_image

    def set_target_image(self, target_image):
        """
        Updates the target docker image
        """
        self.oci_images["target"] = target_image

    def template_manifest(self, manifest_file, **kwargs):
        """
        Reads an YAML manifest and convert it to a string
        templates all variables passed and returns a dict
        """
        self.logger.debug(kwargs)
        data = get_data("illuminatio", f"manifests/{manifest_file}")
        data_str = str(data, "utf-8")

        try:
            return yaml.safe_load(data_str.format(**kwargs))
        except yaml.YAMLError as exc:
            self.logger.error(exc)
            exit(1)

    def refresh_cluster_resources(self, api: k8s.client.CoreV1Api):
        """
        Fetches all pods, services and namespaces from the cluster and updates the corresponding class variables
        """
        format_string = "Found {} {}: {}"
        self.logger.debug("Refreshing cluster resources")
        non_kube_namespace_selector = (
            "metadata.namespace!=kube-system,metadata.namespace!=kube-public"
        )
        pods = api.list_pod_for_all_namespaces(
            field_selector=non_kube_namespace_selector
        ).items
        self.logger.debug(format_string.format(len(pods), "pods", pods))
        svcs = api.list_service_for_all_namespaces(
            field_selector=non_kube_namespace_selector
        ).items
        self.logger.debug(format_string.format(len(svcs), "services", svcs))
        namespaces = api.list_namespace(
            field_selector="metadata.name!=kube-system,metadata.name!=kube-public"
        ).items
        self.logger.debug(
            format_string.format(len(namespaces), "namespaces", namespaces)
        )
        self._current_pods = pods
        self._current_services = svcs
        self.current_namespaces = namespaces

    def namespace_exists(self, name, api: k8s.client.CoreV1Api):
        """
        Check if a namespace exists
        """
        for namespace in self.current_namespaces:
            if namespace.metadata.name != name:
                continue

            self.logger.debug(f"Found namespace {name} in cache")
            return namespace

        resp = None

        try:
            resp = api.read_namespace(name=name)
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                return None

            raise api_exception

        return resp

    def create_namespace(self, name, api: k8s.client.CoreV1Api, labels=None):
        """
        Creates a namespace with the according labels
        """
        # Should we also ensure that the namespace has these labels?
        if labels:
            labels = {CLEANUP_LABEL: CLEANUP_ON_REQUEST}

        namespace = k8s.client.V1Namespace(
            metadata=k8s.client.V1ObjectMeta(name=name, labels=labels)
        )

        try:
            resp = api.create_namespace(body=namespace)
            self.logger.debug(f"Created namespace {resp.metadata.name}")
            self.current_namespaces.append(resp)

            return resp
        except k8s.client.rest.ApiException as api_exception:
            self.logger.error(api_exception)
            exit(1)

    def _rewrite_ports_for_host(self, port_list, services_for_host):
        self.logger.debug("Rewriting portList %s", port_list)
        if not services_for_host:
            # assign random port, a service with matching port will be created
            return {
                p: "%s%s" % (("-" if "-" in p else ""), str(rand_port()))
                for p in port_list
            }
        rewritten_ports = {}
        wild_card_ports = {p for p in port_list if "*" in p}
        numbered_ports = {p for p in port_list if "*" not in p}
        service_ports = [p for svc in services_for_host for p in svc.spec.ports]
        self.logger.debug("Svc ports: %s", service_ports)
        for wildcard_port in wild_card_ports:
            prefix = "-" if "-" in wildcard_port else ""
            # choose any port for wildcard
            rewritten_ports[wildcard_port] = "%s%s" % (
                prefix,
                str(service_ports[0].port),
            )
        for port in numbered_ports:
            prefix = "-" if "-" in port else ""
            port_int = int(port.replace("-", ""))
            service_ports_for_port = [
                p for p in service_ports if p.target_port == port_int
            ]
            # TODO this was a hotfix for recipe 11, where ports 53 were allowed but not for any target,
            # resulting in test to 53 being written despite no service matching them existing.
            # That error should be handled in test generation, an exception here would be fine
            if service_ports_for_port:
                rewritten_ports[port] = "%s%s" % (
                    prefix,
                    str(service_ports_for_port[0].port),
                )
            else:
                # TODO change to exception, handle it higher up
                rewritten_ports[port] = "err"
        return rewritten_ports

    def _get_target_names_creating_them_if_missing(
        self, target_dict, api: k8s.client.CoreV1Api
    ):
        service_names_per_host = {}
        port_dict_per_host = {}
        for host_string in target_dict.keys():
            host = Host.from_identifier(host_string)
            if isinstance(host, GenericClusterHost):
                self.logger.debug(
                    "Found GenericClusterHost %s,"
                    "Rewriting it to a ClusterHost in default namespace now.",
                    host,
                )
                host = ClusterHost("default", host.pod_labels)
            if not isinstance(host, ClusterHost):
                raise ValueError(
                    "Only ClusterHost targets are supported by this Orchestrator."
                    " Host: %s, hostString: %s" % (host, host_string)
                )
            self.logger.debug("Searching service for host %s", host)
            services_for_host = [
                svc for svc in self._current_services if host.matches(svc)
            ]
            self.logger.debug(
                "Found services %s for host %s ",
                [svc.metadata for svc in services_for_host],
                host,
            )
            rewritten_ports = self._rewrite_ports_for_host(
                target_dict[host_string], services_for_host
            )
            self.logger.debug("Rewritten ports: %s", rewritten_ports)
            port_dict_per_host[host_string] = rewritten_ports
            if not services_for_host:
                gen_name = "%s-test-target-pod-" % PROJECT_PREFIX
                target_container = k8s.client.V1Container(
                    image=self.oci_images["target"], name="runner"
                )
                pod_labels_tuple = (ROLE_LABEL, "test_target_pod")
                target_pod = create_pod_manifest(
                    host=host,
                    additional_labels={
                        pod_labels_tuple[0]: pod_labels_tuple[1],
                        CLEANUP_LABEL: CLEANUP_ALWAYS,
                    },
                    generate_name=gen_name,
                    container=target_container,
                )
                target_ports = [
                    int(port.replace("-", ""))
                    for port in port_dict_per_host[host_string].values()
                ]
                # ToDo we should use the cluser ip instead of the DNS names
                # so we don't need the lookups
                service_name = "svc-%s" % convert_to_resource_name(host.to_identifier())
                svc = create_service_manifest(
                    host,
                    {pod_labels_tuple[0]: pod_labels_tuple[1]},
                    {ROLE_LABEL: "test_target_svc", CLEANUP_LABEL: CLEANUP_ALWAYS},
                    service_name,
                    target_ports,
                )
                target_pod_namespace = host.namespace
                service_names_per_host[host_string] = "%s:%s" % (
                    target_pod_namespace,
                    service_name,
                )
                resp = api.create_namespaced_pod(
                    namespace=target_pod_namespace, body=target_pod
                )
                if isinstance(resp, k8s.client.V1Pod):
                    self.logger.debug(
                        "Target pod %s created succesfully", resp.metadata.name
                    )
                    self._current_pods.append(resp)
                else:
                    self.logger.error("Failed to create pod! Resp: %s", resp)
                resp = api.create_namespaced_service(namespace=host.namespace, body=svc)
                if isinstance(resp, k8s.client.V1Service):
                    self.logger.debug(
                        "Target svc %s created succesfully", resp.metadata.name
                    )
                    self._current_services.append(resp)
                else:
                    self.logger.error("Failed to create target svc! Resp: %s", resp)
            else:
                service_names_per_host[host_string] = "%s:%s" % (
                    services_for_host[0].metadata.namespace,
                    services_for_host[0].metadata.name,
                )
        return service_names_per_host, port_dict_per_host

    def _find_or_create_cluster_resources_for_cases(
        self, cases_dict, api: k8s.client.CoreV1Api
    ):
        resolved_cases = {}
        from_host_mappings = {}
        to_host_mappings = {}
        port_mappings = {}
        for from_host_string, target_dict in cases_dict.items():
            from_host = Host.from_identifier(from_host_string)
            self.logger.debug("Searching pod for host %s", from_host)
            if not isinstance(from_host, (ClusterHost, GenericClusterHost)):
                raise ValueError(
                    "Only ClusterHost and GenericClusterHost fromHosts are supported by this Orchestrator"
                )
            namespaces_for_host = self._find_or_create_namespace_for_host(
                from_host, api
            )
            from_host = ClusterHost(
                namespaces_for_host[0].metadata.name, from_host.pod_labels
            )
            self.logger.debug("Updated fromHost with found namespace: %s", from_host)
            pods_for_host = [
                pod for pod in self._current_pods if from_host.matches(pod)
            ]
            # create pod if none for fromHost is in cluster (and add it to podsForHost)
            if not pods_for_host:
                self.logger.debug("Creating dummy pod for host %s", from_host)
                additional_labels = {
                    ROLE_LABEL: "from_host_dummy",
                    CLEANUP_LABEL: CLEANUP_ALWAYS,
                }
                # TODO replace 'dummy' with a more suitable name to prevent potential conflicts
                container = k8s.client.V1Container(
                    image=self.oci_images["target"], name="dummy"
                )
                dummy = create_pod_manifest(
                    from_host, additional_labels, f"{PROJECT_PREFIX}-dummy-", container
                )
                resp = api.create_namespaced_pod(dummy.metadata.namespace, dummy)
                if isinstance(resp, k8s.client.V1Pod):
                    self.logger.debug(
                        "Dummy pod %s created succesfully", resp.metadata.name
                    )
                    pods_for_host = [resp]
                    self._current_pods.append(resp)
                else:
                    self.logger.error("Failed to create dummy pod! Resp: %s", resp)
            else:
                self.logger.debug(
                    "Pods matching %s already exist: ", from_host, pods_for_host
                )
            # resolve target names for fromHost and add them to resolved cases dict
            pod_identifier = "%s:%s" % (
                pods_for_host[0].metadata.namespace,
                pods_for_host[0].metadata.name,
            )
            self.logger.debug("Mapped pod_identifier: %s", pod_identifier)
            from_host_mappings[from_host_string] = pod_identifier
            (
                names_per_host,
                port_names_per_host,
            ) = self._get_target_names_creating_them_if_missing(target_dict, api)
            to_host_mappings[from_host_string] = names_per_host
            port_mappings[from_host_string] = port_names_per_host
            resolved_cases[pod_identifier] = {
                names_per_host[t]: [port_names_per_host[t][p] for p in target_dict[t]]
                for t in target_dict
            }
        return resolved_cases, from_host_mappings, to_host_mappings, port_mappings

    def _find_or_create_namespace_for_host(self, from_host, api):
        namespaces_for_host = [
            ns for ns in self.current_namespaces if from_host.matches(ns)
        ]
        self.logger.debug(
            "Found %s namespaces for host %s: %s",
            len(namespaces_for_host),
            from_host,
            [ns.metadata.name for ns in namespaces_for_host],
        )
        if namespaces_for_host:
            return namespaces_for_host

        self.logger.debug("Creating namespace for host %s", from_host)
        ns_labels = {CLEANUP_LABEL: CLEANUP_ALWAYS}
        if isinstance(from_host, GenericClusterHost):
            namespace_name = convert_to_resource_name(
                labels_to_string(from_host.namespace_labels)
            )
            for key, value in from_host.namespace_labels.items():
                ns_labels[key] = value
        else:
            namespace_name = from_host.namespace
        self.logger.debug(
            "Generated namespace name '%s' for host %s", namespace_name, from_host
        )

        resp = self.namespace_exists(namespace_name, api)
        if resp:
            return [resp]

        resp = self.create_namespace(namespace_name, api, labels=ns_labels)
        return [resp]

    def ensure_cases_are_generated(self, core_api: k8s.client.CoreV1Api):
        """
        Ensures that all required resources for testing are created
        """
        # TODO split up this method
        supported_cases = [
            case for case in self.test_cases if _hosts_are_in_cluster(case)
        ]
        filtered_cases = [
            case for case in self.test_cases if case not in supported_cases
        ]
        self.logger.debug(
            "Filtered %s test cases: %s", len(filtered_cases), filtered_cases
        )
        cases_dict = merge_in_dict(supported_cases)
        self.logger.debug("Created casesDict: %s from %s", cases_dict, supported_cases)
        (
            concrete_cases,
            from_host_mappings,
            to_host_mappings,
            port_mappings,
        ) = self._find_or_create_cluster_resources_for_cases(cases_dict, core_api)
        self.logger.debug("concreteCases: %s", concrete_cases)
        config_map_name = f"{PROJECT_PREFIX}-cases-cfgmap"
        self._create_or_update_case_config_map(
            config_map_name, concrete_cases, core_api
        )

        return from_host_mappings, to_host_mappings, port_mappings, config_map_name

    def ensure_daemonset_is_ready(
        self,
        config_map_name,
        apps_api: k8s.client.AppsV1Api,
        core_api: k8s.client.CoreV1Api,
    ):
        """
        Ensures that all required resources for illuminatio are created
        """
        # Prerequisites for DaemonSet
        service_account_name = f"{PROJECT_PREFIX}-runner"
        self._ensure_service_account_exists(
            core_api, service_account_name, PROJECT_NAMESPACE
        )
        self._ensure_cluster_role_exists()
        self._ensure_cluster_role_binding_exists(
            service_account_name, PROJECT_NAMESPACE
        )

        # Ensure that our DaemonSet and the Pods are running/ready
        daemonset_name = f"{PROJECT_PREFIX}-runner"
        self._ensure_daemonset_exists(
            daemonset_name, service_account_name, config_map_name, apps_api
        )
        pod_selector = self._ensure_daemonset_ready(daemonset_name, apps_api)

        return pod_selector

    def _filter_cluster_cases(self):
        return [
            c
            for c in self.test_cases
            if isinstance(c.fromHost, ClusterHost) and isinstance(c.toHost, ClusterHost)
        ]

    def collect_results(self, pod_selector, api: k8s.client.CoreV1Api):
        """
        Queries pods of runner daemon set and waits for a corresponding configmap for each to be filled.
        Returns the merged data of all configMaps.
        """
        daemon_pods = []
        try:
            daemon_pods = api.list_namespaced_pod(
                PROJECT_NAMESPACE, label_selector=labels_to_string(pod_selector)
            ).items
            self.logger.debug("Found %s daemon runner pods", len(daemon_pods))
        except k8s.client.rest.ApiException as api_exception:
            self.logger.error(api_exception)

        # Todo should we just use labels ?
        expected_result_map_names = [f"{d.metadata.name}-results" for d in daemon_pods]
        result_config_maps = []
        # retry polling results until they are all returned
        while len(result_config_maps) < len(daemon_pods):
            try:
                result_config_maps = [
                    api.read_namespaced_config_map(
                        name=result, namespace=PROJECT_NAMESPACE
                    )
                    for result in expected_result_map_names
                ]
            except k8s.client.rest.ApiException as api_exception:
                if api_exception.reason == "Not Found":
                    pass
                else:
                    raise api_exception
            self.logger.debug(
                "Map names: %s", [m.metadata.name for m in result_config_maps]
            )
            self.logger.debug("Expected names: %s", expected_result_map_names)
            time.sleep(2)
        yamls = [yaml.safe_load(c.data["results"]) for c in result_config_maps]
        self.logger.debug("Found following yamls in result config maps:%s", yamls)
        times = {
            c.metadata.name: yaml.safe_load(c.data["runtimes"])
            for c in result_config_maps
            if "runtimes" in c.data
        }
        return {k: v for yam in [y.items() for y in yamls] for k, v in yam}, times

    def create_daemonset_manifest(
        self, daemon_set_name, service_account_name, config_map_name, container_runtime
    ):
        """
        Creates a DaemonSet manifest on basis of the project's manifest files and the current
        container runtime
        """
        cri_socket = ""
        runtime = ""
        netns_path = "/var/run/netns"

        if container_runtime.startswith("docker"):
            netns_path = "/var/run/docker/netns"
            cri_socket = "/var/run/docker.sock"
            runtime = "docker"
        elif container_runtime.startswith("containerd"):
            # this should be actually the default -> "/run/containerd/containerd.sock"
            cri_socket = "/var/run/dockershim.sock"
            runtime = "containerd"
        else:
            raise NotImplementedError(
                f"Unsupported container runtime: {container_runtime}"
            )

        return self.template_manifest(
            "runner-daemonset.yaml",
            cri_socket=cri_socket,
            netns_path=netns_path,
            runtime=runtime,
            name=daemon_set_name,
            namespace=PROJECT_NAMESPACE,
            image=self.oci_images["runner"],
            service_account_name=service_account_name,
            config_map_name=config_map_name,
        )

    def create_daemonset(self, daemon_manifest, api):
        """
        Creates a DaemonSet on basis of the DaemonSet manifest
        """
        try:
            api.create_namespaced_daemon_set(
                namespace=PROJECT_NAMESPACE, body=daemon_manifest
            )
        except k8s.client.rest.ApiException as api_exception:
            self.logger.error(api_exception)

    def _ensure_daemonset_exists(
        self,
        daemonset_name,
        service_account_name,
        config_map_name,
        api: k8s.client.AppsV1Api,
    ):
        # Use a Kubernetes Manifest as template and replace required parts
        try:
            api.read_namespaced_daemon_set(
                namespace=PROJECT_NAMESPACE, name=daemonset_name
            )
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                daemonset_manifest = self.create_daemonset_manifest(
                    daemonset_name,
                    service_account_name,
                    config_map_name,
                    get_container_runtime(),
                )
                self.create_daemonset(daemonset_manifest, api)
            else:
                raise api_exception

    def _ensure_daemonset_ready(self, daemonset_name, api: k8s.client.AppsV1Api):
        # This should be configurable
        max_tries = 30
        tries = 0
        sleep_time = 5

        self.logger.info(f"Ensure that Pods of DaemonSet {daemonset_name} are ready")
        while tries <= max_tries:
            try:
                daemonset = api.read_namespaced_daemon_set(
                    namespace=PROJECT_NAMESPACE, name=daemonset_name
                )
                ready = daemonset.status.number_ready
                scheduled = daemonset.status.desired_number_scheduled

                # Todo this will print 0/0 if the DaemonSet is not initialized
                self.logger.debug(f"DaemonSet {ready}/{scheduled} Pods are ready")
                if scheduled > 0 and scheduled == ready:
                    return daemonset.spec.selector.match_labels
            except k8s.client.rest.ApiException as api_exception:
                self.logger.error(api_exception)

            time.sleep(sleep_time)
            tries += 1

    def _create_or_update_case_config_map(
        self, config_map_name, cases_dict, api: k8s.client.CoreV1Api
    ):
        cfg_map_meta = k8s.client.V1ObjectMeta(
            namespace=PROJECT_NAMESPACE,
            name=config_map_name,
            labels={CLEANUP_LABEL: CLEANUP_ALWAYS},
        )
        cfg_map = k8s.client.V1ConfigMap(metadata=cfg_map_meta)
        cfg_map.data = {"cases.yaml": yaml.dump(cases_dict)}
        try:
            api.read_namespaced_config_map(
                name=config_map_name, namespace=PROJECT_NAMESPACE
            )
            resp = api.patch_namespaced_config_map(
                config_map_name, PROJECT_NAMESPACE, cfg_map
            )
            if isinstance(resp, k8s.client.V1ConfigMap):
                self.logger.debug("Patched config map with test cases")
                self.logger.debug(resp)
            else:
                raise Exception("Failed to patch cases ConfigMap")
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                resp = api.create_namespaced_config_map(
                    cfg_map.metadata.namespace, cfg_map
                )
                if isinstance(resp, k8s.client.V1ConfigMap):
                    self.logger.debug("Created config map with test cases")
                else:
                    raise Exception("Failed to create cases ConfigMap")
            else:
                raise api_exception

    def _ensure_cluster_role_binding_exists(self, service_account_name, namespace):
        rbac_api = k8s.client.RbacAuthorizationV1Api()
        # TODO consider extracting crb_name into a cli parameter
        crb_name = "%s-runner-crb" % PROJECT_PREFIX
        try:
            cluster_role_binding = rbac_api.read_cluster_role_binding(name=crb_name)
            cluster_role_binding = update_role_binding_manifest(
                cluster_role_binding, namespace, service_account_name
            )
            rbac_api.patch_cluster_role_binding(crb_name, cluster_role_binding)
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                self.logger.debug("Creating cluster role binding")
                crb = create_role_binding_manifest_for_service_account(
                    namespace, crb_name, service_account_name
                )
                rbac_api.create_cluster_role_binding(crb)
            else:
                self.logger.info("Exception reason: %s", api_exception.reason)
                raise api_exception

    def _ensure_cluster_role_exists(self):
        rbac_api = k8s.client.RbacAuthorizationV1Api()
        # TODO we should read the role instead just trying to create it
        try:
            cluster_role_dict = self.template_manifest("cluster-role.yaml")
            rbac_api.create_cluster_role(body=cluster_role_dict)
        except k8s.client.rest.ApiException as api_exception:
            json_body = json.loads(api_exception.body)
            self.logger.debug("ApiException Body:\n%s\n", json_body)
            if json_body.get("reason", "") == "AlreadyExists":
                self.logger.debug("Using existing cluster role")
            else:
                self.logger.error("Error creating cluster role: %s\n", api_exception)

    def _ensure_service_account_exists(self, api, service_account_name, namespace):
        """
        Ensure that the specified kubernetes ServiceAccount exists
        This doesn't check if the existing service account is different
        We could use patch_namespaced_service_account to ensure it's content matches
        """
        try:
            # check whether the service account already exists
            api.read_namespaced_service_account(
                name=service_account_name, namespace=namespace
            )
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                # it does not exists, so we have to freshly create it
                service_account = create_service_account_manifest_for_runners(
                    service_account_name, namespace
                )
                resp = api.create_namespaced_service_account(namespace, service_account)
                if isinstance(resp, k8s.client.V1ServiceAccount):
                    self.logger.debug(
                        "Succesfully created ServiceAccount for namespace %s", namespace
                    )
                else:
                    self.logger.error(
                        "Could not create ServiceAccount for namespace %s Resp: %s",
                        namespace,
                        resp,
                    )
            else:
                raise api_exception


def convert_to_resource_name(string):
    """
    Deletes commas and equal signs,
    replaces colons with dashes and * with "any"
    """
    return (
        string.replace(":", "-").replace(",", "").replace("=", "").replace("*", "any")
    )
