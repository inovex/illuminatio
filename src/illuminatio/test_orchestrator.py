import time
import yaml
import json
import kubernetes as k8s
from illuminatio.host import ClusterHost, GenericClusterHost, Host
from illuminatio.k8s_util import init_pod, init_role_binding_for_service_account, \
    init_service_account_for_runners, init_svc, labels_to_string, update_role_binding
from illuminatio.test_case import merge_in_dict
from illuminatio.util import PROJECT_NAMESPACE, PROJECT_PREFIX, CLEANUP_LABEL, ROLE_LABEL, CLEANUP_ALWAYS, \
    CLEANUP_ON_REQUEST, DAEMONSET_NAME
from illuminatio.util import rand_port
from pkgutil import get_data


def get_container_runtime():
    api = k8s.client.CoreV1Api()
    node_list = api.list_node()
    if node_list.items:
        container_runtime_name = node_list.items[0].status.node_info.container_runtime_version
        for node in node_list.items:
            if node.status.node_info.container_runtime_version != container_runtime_name:
                raise ValueError("Different container runtime versions found on your nodes")
        return container_runtime_name
    else:
        raise ValueError("Node not found")


def getManifest(yaml_filename):
    manifests_path = 'manifests/'
    data = get_data('illuminatio', manifests_path + yaml_filename)
    daemonset_manifest = None
    try:
        daemonset_manifest = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        print(exc)
    return daemonset_manifest


class NetworkTestOrchestrator:
    logger = None

    def __init__(self, test_cases, log):
        self._test_cases = test_cases
        self._current_pods = []
        self._current_services = []
        self._current_namespaces = []
        self.runner_daemon_set = None
        self.runner_image = ""
        self.target_image = ""
        global logger
        logger = log

    def set_runner_image(self, runner_image):
        self.runner_image = runner_image

    def set_target_image(self, target_image):
        self.target_image = target_image

    def refresh_cluster_resources(self, api: k8s.client.CoreV1Api):
        format_string = "Found {} {}: {}"
        logger.debug("Refreshing cluster resources")
        non_kube_namespace_selector = "metadata.namespace!=kube-system,metadata.namespace!=kube-public"
        pods = api.list_pod_for_all_namespaces(field_selector=non_kube_namespace_selector).items
        logger.debug(format_string.format(len(pods), "pods", pods))
        svcs = api.list_service_for_all_namespaces(field_selector=non_kube_namespace_selector).items
        logger.debug(format_string.format(len(svcs), "services", svcs))
        namespaces = api.list_namespace(field_selector="metadata.name!=kube-system,metadata.name!=kube-public").items
        logger.debug(format_string.format(len(namespaces), "namespaces", namespaces))
        self._current_pods = pods
        self._current_services = svcs
        self._current_namespaces = namespaces

    def _rewrite_ports_for_host(self, port_list, services_for_host):
        logger.debug("Rewriting portList " + str(port_list))
        if not services_for_host:
            # assign random port, a service with matching port will be created
            return {p: ("-" if "-" in p else "") + str(rand_port()) for p in port_list}
        else:
            rewritten_ports = {}
            wild_card_ports = set([p for p in port_list if "*" in p])
            numbered_ports = set([p for p in port_list if "*" not in p])
            service_ports = [p for svc in services_for_host for p in svc.spec.ports]
            logger.debug("Svc ports: " + str(service_ports))
            for wildcard_port in wild_card_ports:
                prefix = "-" if "-" in wildcard_port else ""
                # choose any port for wildcard
                rewritten_ports[wildcard_port] = prefix + str(service_ports[0].port)
            for port in numbered_ports:
                prefix = "-" if "-" in port else ""
                port_int = int(port.replace("-", ""))
                service_ports_for_port = [p for p in service_ports if p.target_port == port_int]
                # TODO this was a hotfix for recipe 11, where ports 53 were allowed but not for any target,
                # resulting in test to 53 being written despite no service matching them existing.
                # That error should be handled in test generation, an exception here would be fine
                if service_ports_for_port:
                    rewritten_ports[port] = prefix + str(service_ports_for_port[0].port)
                else:
                    # TODO change to exception, handle it higher up
                    rewritten_ports[port] = "err"
            return rewritten_ports

    def _get_target_names_creating_them_if_missing(self, target_dict, api: k8s.client.CoreV1Api):
        svc_names_per_host = {}
        port_dict_per_host = {}
        for host_string in target_dict.keys():
            host = Host.from_identifier(host_string)
            if isinstance(host, GenericClusterHost):
                logger.debug("Found GenericClusterHost " + str(
                    host) + ". Rewriting it to a ClusterHost in default namespace now.")
                host = ClusterHost("default", host.pod_labels)
            if not isinstance(host, ClusterHost):
                raise ValueError("Only ClusterHost targets are supported by this Orchestrator. Host: " + str(
                    host) + ", hostString: " + host_string)
            logger.debug("Searching service for host " + str(host))
            services_for_host = [svc for svc in self._current_services if host.matches(svc)]
            logger.debug("Found services {} for host {} ".format([svc.metadata for svc in services_for_host], host))
            rewritten_ports = self._rewrite_ports_for_host(target_dict[host_string], services_for_host)
            logger.debug("Rewritten ports: " + str(rewritten_ports))
            port_dict_per_host[host_string] = rewritten_ports
            if not services_for_host:
                gen_name = PROJECT_PREFIX + "-test-target-pod-"
                target_container = k8s.client.V1Container(image=self.target_image, name="runner")
                pod_labels_tuple = (ROLE_LABEL, "test_target_pod")
                target_pod = init_pod(host=host, additional_labels={pod_labels_tuple[0]: pod_labels_tuple[1],
                                                                    CLEANUP_LABEL: CLEANUP_ALWAYS},
                                      generate_name=gen_name,
                                      container=target_container)
                target_ports = [int(port.replace("-", "")) for port in port_dict_per_host[host_string].values()]
                # ToDo we should use the cluser ip instead of the DNS names
                # so we don't need the lookups
                svc_name = "svc-" + convert_to_resource_name(host.to_identifier())
                svc = init_svc(host, {pod_labels_tuple[0]: pod_labels_tuple[1]},
                               {ROLE_LABEL: "test_target_svc", CLEANUP_LABEL: CLEANUP_ALWAYS}, svc_name, target_ports)
                target_pod_namespace = host.namespace
                svc_names_per_host[host_string] = target_pod_namespace + ":" + svc_name
                resp = api.create_namespaced_pod(namespace=target_pod_namespace, body=target_pod)
                if isinstance(resp, k8s.client.V1Pod):
                    logger.debug("Target pod " + resp.metadata.name + " created succesfully")
                    self._current_pods.append(resp)
                else:
                    logger.error("Failed to create pod! Resp: " + str(resp))
                resp = api.create_namespaced_service(namespace=host.namespace, body=svc)
                if isinstance(resp, k8s.client.V1Service):
                    logger.debug("Target svc " + resp.metadata.name + " created succesfully")
                    self._current_services.append(resp)
                else:
                    logger.error("Failed to create target svc! Resp: " + str(resp))
            else:
                svc_names_per_host[host_string] = services_for_host[0].metadata.namespace + ":" + services_for_host[
                    0].metadata.name
        return svc_names_per_host, port_dict_per_host

    def _find_or_create_cluster_resources_for_cases(self, cases_dict, api: k8s.client.CoreV1Api):
        resolved_cases = {}
        from_host_mappings = {}
        to_host_mappings = {}
        port_mappings = {}
        for from_host_string, target_dict in cases_dict.items():
            from_host = Host.from_identifier(from_host_string)
            logger.debug("Searching pod for host " + str(from_host))
            if not (isinstance(from_host, ClusterHost) or isinstance(from_host, GenericClusterHost)):
                raise ValueError("Only ClusterHost and GenericClusterHost fromHosts are supported by this Orchestrator")
            namespaces_for_host = self._find_or_create_namespace_for_host(from_host, api)
            from_host = ClusterHost(namespaces_for_host[0].metadata.name, from_host.pod_labels)
            logger.debug("Updated fromHost with found namespace: " + str(from_host))
            pods_for_host = [pod for pod in self._current_pods if from_host.matches(pod)]
            # create pod if none for fromHost is in cluster (and add it to podsForHost)
            if not pods_for_host:
                logger.debug("Creating dummy pod for host " + str(from_host))
                additional_labels = {ROLE_LABEL: "from_host_dummy", CLEANUP_LABEL: CLEANUP_ALWAYS}
                container = k8s.client.V1Container(image="nginx:stable", name="dummy")
                dummy = init_pod(from_host, additional_labels, PROJECT_PREFIX + "-dummy-", container)
                resp = api.create_namespaced_pod(dummy.metadata.namespace, dummy)
                if isinstance(resp, k8s.client.V1Pod):
                    logger.debug("Dummy pod " + resp.metadata.name + " created succesfully")
                    pods_for_host = [resp]
                    self._current_pods.append(resp)
                else:
                    logger.error("Failed to create dummy pod! Resp: " + str(resp))
            else:
                logger.debug("Pods matching " + str(from_host) + " already exist: " + str(pods_for_host))
            # resolve target names for fromHost and add them to resolved cases dict
            pod_identifier = pods_for_host[0].metadata.namespace + ":" + pods_for_host[0].metadata.name
            logger.debug("Mapped pod_identifier: " + str(pod_identifier))
            from_host_mappings[from_host_string] = pod_identifier
            names_per_host, port_names_per_host = self._get_target_names_creating_them_if_missing(target_dict, api)
            to_host_mappings[from_host_string] = names_per_host
            port_mappings[from_host_string] = port_names_per_host
            resolved_cases[pod_identifier] = {names_per_host[t]: [port_names_per_host[t][p] for p in target_dict[t]]
                                              for t in target_dict}
        return resolved_cases, from_host_mappings, to_host_mappings, port_mappings

    def _find_or_create_namespace_for_host(self, from_host, api):
        namespaces_for_host = [ns for ns in self._current_namespaces if from_host.matches(ns)]
        logger.debug("Found {} namespaces for host {}: {}".format(len(namespaces_for_host), from_host,
                                                                  [ns.metadata.name for ns in namespaces_for_host]))
        if namespaces_for_host:
            return namespaces_for_host
        else:
            logger.debug("Creating namespace for host " + str(from_host))
            ns_labels = {ROLE_LABEL: "testing_namespace", CLEANUP_LABEL: CLEANUP_ALWAYS}
            if isinstance(from_host, GenericClusterHost):
                namespace_name = convert_to_resource_name(labels_to_string(from_host.namespace_labels))
                for k, v in from_host.namespace_labels.items():
                    ns_labels[k] = v
            else:
                namespace_name = from_host.namespace
            logger.debug("Generated namespace name '" + str(namespace_name) + "' for host " + str(from_host))
            resp = api.create_namespace(
                k8s.client.V1Namespace(metadata=k8s.client.V1ObjectMeta(name=namespace_name, labels=ns_labels)))
            if isinstance(resp, k8s.client.V1Namespace):
                logger.debug(
                    "Test namespace " + resp.metadata.name + " created succesfully, adding it to namespace list")
                self._current_namespaces.append(resp)
                time.sleep(1)
                while not api.list_namespaced_service_account(resp.metadata.name,
                                                              field_selector="metadata.name=default").items:
                    logger.debug(
                        "Waiting for kubernetes to create default service account for namespace " + resp.metadata.name)
                    time.sleep(2)
                return [resp]
            else:
                logger.error("Failed to create test namespace for {}! Resp: {}".format(from_host, resp))
                return []

    # TODO refactor with above method / at least use already polled namespaces in self._currentNamespaces
    def _create_project_namespace_if_missing(self, api: k8s.client.CoreV1Api):
        namespace_labels = {ROLE_LABEL: "daemon-runner-namespace", CLEANUP_LABEL: CLEANUP_ON_REQUEST}
        namespace_list = api.list_namespace(label_selector=labels_to_string(namespace_labels))
        if not namespace_list.items:
            namespace = k8s.client.V1Namespace(
                metadata=k8s.client.V1ObjectMeta(name=PROJECT_NAMESPACE, labels=namespace_labels))
            api.create_namespace(namespace)

    def create_and_launch_daemon_set_runners(self, apps_api: k8s.client.AppsV1Api, core_api: k8s.client.CoreV1Api):
        """ Creates DaemonSet for testing pods that already in the cluster. """
        supported_cases = [c for c in self._test_cases if self._hosts_are_in_cluster(c)]
        filtered_cases = [c for c in self._test_cases if c not in supported_cases]
        logger.debug("Filtered " + str(len(filtered_cases)) + " test cases: " + str(filtered_cases))
        cases_dict = merge_in_dict(supported_cases)
        logger.debug("Created casesDict: " + str(cases_dict) + " from " + str(supported_cases))
        concrete_cases, from_host_mappings, to_host_mappings, port_mappings = \
            self._find_or_create_cluster_resources_for_cases(cases_dict, core_api)
        logger.debug("concreteCases: " + str(concrete_cases))
        self._create_project_namespace_if_missing(core_api)
        config_map_name = PROJECT_PREFIX + "-cases-cfgmap"
        self._create_or_update_case_config_map(config_map_name, concrete_cases, core_api)

        service_account_name = PROJECT_PREFIX + "-runner"
        self._create_missing_service_accounts(core_api, service_account_name, PROJECT_NAMESPACE)
        self._create_missing_cluster_role()
        self._create_missing_cluster_role_binding(service_account_name, PROJECT_NAMESPACE)

        self._create_daemon_set_if_missing(service_account_name, config_map_name, apps_api)
        return from_host_mappings, to_host_mappings, port_mappings

    def _hosts_are_in_cluster(self, c):
        return all([(isinstance(h, ClusterHost)) or isinstance(h, GenericClusterHost)
                    for h in [c.from_host, c.to_host]])

    def _filter_cluster_cases(self):
        return [c for c in self._test_cases if
                isinstance(c.fromHost, ClusterHost) and isinstance(c.toHost, ClusterHost)]

    def collect_results(self, api: k8s.client.CoreV1Api):
        """ Queries pods of runner daemon set and waits for a corresponding configmap for each to be filled.
            Returns the merged data of all configMaps. """
        # Todo fix me!
        # api.list_node(label_selector="!node-role.kubernetes.io/master").items
        non_master_nodes = api.list_node().items
        logger.debug("Found " + str(len(non_master_nodes)) + " non master nodes")
        daemon_pods = []
        # we re-request daemon pods until the number exactly match because pods are sometimes overprovisioned
        # and then immediately deleted, causing the target number of ConfigMaps to never be reached
        apps_api = k8s.client.AppsV1Api()
        while self.runner_daemon_set is None:
            logger.info("Waiting for runner_daemon_set to become initialized")
            try:
                self.runner_daemon_set = apps_api.read_namespaced_daemon_set(namespace=PROJECT_NAMESPACE,
                                                                             name=DAEMONSET_NAME)
                if isinstance(self.runner_daemon_set, k8s.client.V1DaemonSet):
                    break
            except k8s.client.rest.ApiException as api_exception:
                logger.info("exception occured!")
                if api_exception.reason != "Not Found":
                    raise(api_exception)
            time.sleep(1)

        while len(daemon_pods) != len(non_master_nodes):
            daemon_pods = api.list_namespaced_pod(PROJECT_NAMESPACE, label_selector=labels_to_string(
                self.runner_daemon_set.spec.selector.match_labels)).items
            logger.debug("Found " + str(len(daemon_pods)) + " daemon runner pods")
            time.sleep(2)
        expected_result_map_names = [d.metadata.name + "-results" for d in daemon_pods]
        result_config_maps = []
        # retry polling results until they are all returned
        while len(result_config_maps) < len(daemon_pods):
            try:
                result_config_maps = [api.read_namespaced_config_map(name=result, namespace=PROJECT_NAMESPACE)
                                      for result in expected_result_map_names]
            except k8s.client.rest.ApiException as api_exception:
                if api_exception.reason == "Not Found":
                    pass
                else:
                    raise(api_exception)
            logger.debug("Map names: " + str([m.metadata.name for m in result_config_maps]))
            logger.debug("Expected names: " + str(expected_result_map_names))
            time.sleep(2)
        yamls = [yaml.safe_load(c.data["results"]) for c in result_config_maps]
        logger.debug("Found following yamls in result config maps:" + str(yamls))
        times = {c.metadata.name: yaml.safe_load(c.data["runtimes"])
                 for c in result_config_maps if "runtimes" in c.data}
        return {k: v for yam in [y.items() for y in yamls] for k, v in yam}, times

    def createDaemonset(self, daemon_set_name, service_account_name, config_map_name, api):
        # load suitable manifest
        container_runtime_version = get_container_runtime()
        if container_runtime_version.startswith("docker"):
            daemon_set_dict = getManifest("docker-daemonset.yaml")
        elif container_runtime_version.startswith("containerd"):
            daemon_set_dict = getManifest("containerd-daemonset.yaml")
        else:
            raise NotImplementedError("Unsupported container runtime: %s" % container_runtime_version)

        # adapt non-static values
        daemon_set_dict["metadata"]["name"] = daemon_set_name
        daemon_set_dict["metadata"]["namespace"] = PROJECT_NAMESPACE
        daemon_set_dict["spec"]["template"]["spec"]["containers"][0]["image"] = self.runner_image
        daemon_set_dict["spec"]["template"]["spec"]["containers"][0]["imagePullPolicy"] = "Always"
        daemon_set_dict["spec"]["template"]["spec"]["containers"][0]["name"] = "runner"
        daemon_set_dict["spec"]["template"]["spec"]["serviceAccount"] = service_account_name
        daemon_set_dict["spec"]["template"]["spec"]["volumes"][0]["configMap"]["name"] = config_map_name
        daemon_set_dict["spec"]["template"]["spec"]["dnsPolicy"] = "ClusterFirst"
        daemon_set_dict["spec"]["template"]["metadata"]["generateName"] = PROJECT_PREFIX + "-ds-runner"
        logger.debug("daemonset_dict:\n%s" % daemon_set_dict)
        # create daemon set
        daemonset = api.create_namespaced_daemon_set(namespace=PROJECT_NAMESPACE, body=daemon_set_dict)
        if isinstance(daemonset, k8s.client.V1DaemonSet):
            logger.debug("Succesfully created test runner DaemonSet " + daemonset.metadata.name)
            self.runner_daemon_set = daemonset
        else:
            logger.error("Failed to create test runner DaemonSet: " + str(daemonset))

    def _create_daemon_set_if_missing(self, service_account_name, config_map_name, api: k8s.client.AppsV1Api):
        # Use a Kubernetes Manifest as template and replace requiered parts:
        # e.g. https://github.com/kubernetes-client/python/blob/master/examples/create_deployment_from_yaml.py
        try:
            # read existing daemon set
            daemonset = api.read_namespaced_daemon_set(namespace=PROJECT_NAMESPACE, name=DAEMONSET_NAME)
            if isinstance(daemonset, k8s.client.V1DaemonSet):
                logger.debug("Succesfully read existing test runner DaemonSet " + daemonset.metadata.name)
                self.runner_daemon_set = daemonset
            else:
                logger.error("Failed to read existing test runner DaemonSet: " + str(daemonset))
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                self.createDaemonset(DAEMONSET_NAME, service_account_name, config_map_name, api)
                pass
            else:
                raise(api_exception)

    def _create_or_update_case_config_map(self, config_map_name, cases_dict, api: k8s.client.CoreV1Api):
        cfg_map_meta = k8s.client.V1ObjectMeta(namespace=PROJECT_NAMESPACE, name=config_map_name,
                                               labels={CLEANUP_LABEL: CLEANUP_ALWAYS})
        cfg_map = k8s.client.V1ConfigMap(metadata=cfg_map_meta)
        cfg_map.data = {"cases.yaml": yaml.dump(cases_dict)}
        try:
            api.read_namespaced_config_map(name=config_map_name, namespace=PROJECT_NAMESPACE)
            resp = api.patch_namespaced_config_map(config_map_name, PROJECT_NAMESPACE, cfg_map)
            if isinstance(resp, k8s.client.V1ConfigMap):
                logger.debug("Patched config map with test cases")
                logger.debug(resp)
            else:
                raise Exception("Failed to patch cases ConfigMap")
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                resp = api.create_namespaced_config_map(cfg_map.metadata.namespace, cfg_map)
                if isinstance(resp, k8s.client.V1ConfigMap):
                    logger.debug("Created config map with test cases")
                else:
                    raise Exception("Failed to create cases ConfigMap")
            else:
                raise(api_exception)

    def _create_missing_cluster_role_binding(self, service_account_name, namespace):
        rbac_api = k8s.client.RbacAuthorizationV1Api()
        # TODO consider extracting crb_name into a cli parameter
        crb_name = PROJECT_PREFIX + "-runner-crb"
        try:
            cluster_role_binding = rbac_api.read_cluster_role_binding(name=crb_name)
            cluster_role_binding = update_role_binding(cluster_role_binding, namespace, service_account_name)
            rbac_api.patch_cluster_role_binding(crb_name, cluster_role_binding)
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                logger.info("Creating cluster role binding")
                crb = init_role_binding_for_service_account(namespace, crb_name, service_account_name)
                rbac_api.create_cluster_role_binding(crb)
                pass
            else:
                logger.info("exception reason: " + api_exception.reason)
                raise api_exception

    def _create_missing_cluster_role(self):
        rbac_api = k8s.client.RbacAuthorizationV1Api()
        try:
            cluster_role_dict = getManifest("cluster-role.yaml")
            rbac_api.create_cluster_role(body=cluster_role_dict)
        except k8s.client.rest.ApiException as e:
            json_body = json.loads(e.body)
            logger.debug("ApiException Body:\n%s\n" % json_body)
            if json_body.get("reason", "") == "AlreadyExists":
                logger.info("Using existing cluster role")
                pass
            else:
                print("Error creating cluster role: %s\n" % e)

    def _create_missing_service_accounts(self, api, service_account_name, namespace):
        try:
            service_account = api.read_namespaced_service_account(name=service_account_name, namespace=namespace)
        except k8s.client.rest.ApiException as api_exception:
            if api_exception.reason == "Not Found":
                service_account = init_service_account_for_runners(service_account_name, namespace)
                resp = api.create_namespaced_service_account(namespace, service_account)
                if isinstance(resp, k8s.client.V1ServiceAccount):
                    logger.debug("Succesfully created service account for namespace " + namespace)
                else:
                    logger.error("Could not create service account for namespace " + namespace + " Resp: " + str(resp))
            else:
                raise api_exception


def convert_to_resource_name(string):
    return string.replace(":", "-").replace(",", "").replace("=", "").replace("*", "any")
