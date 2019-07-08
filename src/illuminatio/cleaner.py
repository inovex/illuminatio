import logging
import time

from illuminatio.k8s_util import labels_to_string
from illuminatio.util import CLEANUP_LABEL


class Cleaner:

    def __init__(self, core_api, apps_api, rbac_api, logger=None):
        if logger is None:
            logger = logging.getLogger()
        self.logger = logger
        self.core_api = core_api
        self.apps_api = apps_api
        self.rbac_api = rbac_api

    def clean_up_pods_in_namespaces(self, namespaces, cleanup_policy):
        return self.delete_res_using(namespaces, cleanup_policy, self.core_api.delete_collection_namespaced_pod, "pod")

    def clean_up_services_in_namespaces(self, namespaces, cleanup_policy):
        def delete_collection_namespaced_serivce(namespace, label_selector=None):
            if label_selector is None:
                label_selector = labels_to_string({CLEANUP_LABEL: cleanup_policy})
            resps = []
            svcs = self.core_api.list_namespaced_service(namespace, label_selector=label_selector)
            for svc in svcs.items:
                resps.append(self.core_api.delete_namespaced_service(svc.metadata.name, namespace))
            return resps

        return self.delete_res_using(namespaces, cleanup_policy, delete_collection_namespaced_serivce, "svc")

    def clean_up_cfg_maps_in_namespaces(self, namespaces, cleanup_policy):
        return self.delete_res_using(namespaces, cleanup_policy,
                                     self.core_api.delete_collection_namespaced_config_map, "CfgMap")

    def clean_up_cluster_role_binding(self, cleanup_policy):
        self.logger.info("Deleting CRBs  with cleanup policy %s globally", cleanup_policy)
        res = self.rbac_api.delete_collection_cluster_role_binding(
            label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy}))
        self.logger.debug(res)
        return [res]

    def clean_up_service_accounts_in_namespaces(self, namespaces, cleanup_policy):
        return self.delete_res_using(namespaces, cleanup_policy,
                                     self.core_api.delete_collection_namespaced_service_account, "SA")

    def clean_up_daemon_sets_in_namespaces(self, namespaces, cleanup_policy):
        return self.delete_res_using(namespaces, cleanup_policy,
                                     self.apps_api.delete_collection_namespaced_daemon_set, "DS")

    def clean_up_namespaces(self, cleanup_policy):
        resps = []
        namespaces = self.core_api.list_namespace(
            label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy})).items
        namespace_names = [n.metadata.name for n in namespaces]
        self.logger.info("Deleting namespacess %s with cleanup policy %s", str(namespace_names), cleanup_policy)
        for namespace in namespaces:
            resp = self.core_api.delete_namespace(namespace.metadata.name, propagation_policy="Background")
            resps.append(resp)
        while self.core_api.list_namespace(label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy})).items:
            self.logger.debug("Waiting for namespaces {} to be deleted.".format(namespace_names))
            time.sleep(2)
        return resps

    def delete_res_using(self, namespaces, cleanup_policy, method, res_name):
        resps = []
        for namespace in namespaces:
            self.logger.info("Deleting " + res_name + "s in " + str(namespace)
                             + " with cleanup policy " + cleanup_policy)
            resp = method(namespace, label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy}))
            self.logger.debug(resp)
            resps.append(resp)
        return resps
