"""
Contains the routines to completely clean up all resources generated by illuminatio
"""
import logging
import time

import kubernetes
from illuminatio.k8s_util import labels_to_string
from illuminatio.util import CLEANUP_LABEL


class Cleaner:
    """
    This class provides functionalities to delete resources in a
    kubernetes cluster which have been created by illuminatio
    """

    def __init__(self, core_api, apps_api, rbac_api, logger=None):
        if logger is None:
            logger = logging.getLogger()
        self.logger = logger
        self.core_api = core_api
        self.apps_api = apps_api
        self.rbac_api = rbac_api

    def clean_up_pods_in_namespaces(self, namespaces, cleanup_policy):
        """
        Deletes all pods in a list of namespaces
        """
        return self.delete_resource_with_cleanup_policy(
            namespaces,
            cleanup_policy,
            self.core_api.delete_collection_namespaced_pod,
            "pod",
        )

    def clean_up_services_in_namespaces(self, namespaces, cleanup_policy):
        """
        Deletes all services in a list of namespaces
        """

        def delete_collection_namespaced_service(namespace, label_selector=None):
            """
            Wrapper Method for deleting namespaced services by label,
            as delete_namespaced_service does not provide this feature.
            """
            if label_selector is None:
                label_selector = labels_to_string({CLEANUP_LABEL: cleanup_policy})
            responses = []
            svcs = self.core_api.list_namespaced_service(
                namespace, label_selector=label_selector
            )
            for svc in svcs.items:
                responses.append(
                    self.core_api.delete_namespaced_service(
                        svc.metadata.name, namespace
                    )
                )
            return responses

        return self.delete_resource_with_cleanup_policy(
            namespaces, cleanup_policy, delete_collection_namespaced_service, "svc"
        )

    def clean_up_cfg_maps_in_namespaces(self, namespaces, cleanup_policy):
        """
        Deletes all ConfigMaps in a list of namespaces
        """
        return self.delete_resource_with_cleanup_policy(
            namespaces,
            cleanup_policy,
            self.core_api.delete_collection_namespaced_config_map,
            "CfgMap",
        )

    def clean_up_cluster_role_binding_with_cleanup_policy(self, cleanup_policy):
        """
        Deletes all cluster role bindings matching the given cleanup policy
        """
        self.logger.debug(
            "Deleting CRDs with cleanup policy %s globally", cleanup_policy
        )
        res = self.rbac_api.delete_collection_cluster_role_binding(
            label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy})
        )
        self.logger.debug(res)
        return [res]

    def clean_up_service_accounts_in_namespaces_with_cleanup_policy(
        self, namespaces, cleanup_policy
    ):
        """
        Deletes all ServiceAccounts in a list of namespaces matching the given cleanup policy
        """
        return self.delete_resource_with_cleanup_policy(
            namespaces,
            cleanup_policy,
            self.core_api.delete_collection_namespaced_service_account,
            "SA",
        )

    def clean_up_daemon_sets_in_namespaces_with_cleanup_policy(
        self, namespaces, cleanup_policy
    ):
        """
        Deletes all DaemonSets in a list of namespaces matching the given cleanup policy
        """
        return self.delete_resource_with_cleanup_policy(
            namespaces,
            cleanup_policy,
            self.apps_api.delete_collection_namespaced_daemon_set,
            "DS",
        )

    def clean_up_namespaces_with_cleanup_policy(self, cleanup_policy):
        """
        Deletes all namespaces matching the given cleanup policy
        """
        responses = []
        namespaces = self.core_api.list_namespace(
            label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy})
        ).items
        namespace_names = [n.metadata.name for n in namespaces]
        self.logger.debug(
            "Deleting namespaces %s with cleanup policy %s",
            namespace_names,
            cleanup_policy,
        )
        for namespace in namespaces:
            resp = self.core_api.delete_namespace(
                namespace.metadata.name, propagation_policy="Background"
            )
            responses.append(resp)
        while self.core_api.list_namespace(
            label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy})
        ).items:
            self.logger.debug(
                "Waiting for namespaces %s to be deleted.", namespace_names
            )

        # TODO ugly hack to prevent race conditions when deleting namespaces
        time.sleep(2)
        return responses

    def delete_resource_with_cleanup_policy(
        self, namespaces, cleanup_policy, method, resource_name
    ):
        """
        Deletes all resources which match the given cleanup policy
        """
        responses = []
        for namespace in namespaces:
            self.logger.debug(
                "Deleting %s in namespace %s with cleanup policy %s",
                resource_name,
                namespace,
                cleanup_policy,
            )
            try:
                resp = method(
                    namespace,
                    label_selector=labels_to_string({CLEANUP_LABEL: cleanup_policy}),
                )
                responses.append(resp)
            except kubernetes.client.rest.ApiException:
                self.logger.error(
                    "An error occured trying to delete the marked resource."
                )
        return responses
