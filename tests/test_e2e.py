import concurrent.futures
import re
from os import path

import time
import yaml
import pytest
import subprocess
from kubernetes import client, config, utils
from kubernetes.utils.create_from_yaml import FailToCreateError

@pytest.mark.e2e
def test_deny_all_traffic_to_an_application():
    config.load_kube_config()
    k8s_client = client.ApiClient()
    create_from_yaml(k8s_client,
                           "e2e-manifests/01-deny-all-traffic-to-an-application.yml",
                           verbose=False, wait_until_ready=True)
    results_yaml_file = "result.yml"
    # run illuminatio and store the results to a yaml file
    res = subprocess.run(["illuminatio", "clean", "run", "--runner-image=localhost:5000/illuminatio-runner:dev",
                          "-o", results_yaml_file],
                         capture_output=True,
                         timeout=60)
    assert res.returncode == 0

    # evaluate the results of illuminatio
    with open(path.abspath(results_yaml_file)) as f:
        yaml_document = yaml.safe_load_all(f)
        for results_dict in yaml_document:
            if results_dict["cases"] is None:
                raise ValueError("Error: Invalid output, test cases seem to be missing")
            cases_dict = results_dict["cases"]
            for case in cases_dict:
                raw_case = cases_dict[case]
                for namespace in raw_case:
                    result = raw_case[namespace]
                    for ports in result:
                        success = result[ports]["success"]
                        if success != True:
                            raise ValueError("Error: One or more test cases of illuminatio have failed")

    # Clean up
    res = subprocess.run(["illuminatio", "clean"], capture_output=True)
    assert res.returncode == 0
    print(res.stdout)

    # Clean up
    res = subprocess.run(["kubectl", "delete", "-f", "e2e-manifests/01-deny-all-traffic-to-an-application.yml"],
                         capture_output=True,
                         timeout=60)

    assert res.returncode == 0
    # ToDo evaluate result
    print(res.stdout)

# TODO extract util functions into test_util.py

def create_from_yaml(
        k8s_client,
        yaml_file,
        verbose=False,
        namespace="default",
        wait_until_ready=False,
        **kwargs):
    """
    Perform an action from a yaml file. Pass True for verbose to
    print confirmation information.
    Input:
    yaml_file: string. Contains the path to yaml file.
    k8s_client: an ApiClient object, initialized with the client args.
    verbose: If True, print confirmation from the create action.
        Default is False.
    namespace: string. Contains the namespace to create all
        resources inside. The namespace must preexist otherwise
        the resource creation will fail. If the API object in
        the yaml file already contains a namespace definition
        this parameter has no effect.
    Available parameters for creating <kind>:
    :param async_req bool
    :param bool include_uninitialized: If true, partially initialized
        resources are included in the response.
    :param str pretty: If 'true', then the output is pretty printed.
    :param str dry_run: When present, indicates that modifications
        should not be persisted. An invalid or unrecognized dryRun
        directive will result in an error response and no further
        processing of the request.
        Valid values are: - All: all dry run stages will be processed
    Raises:
        FailToCreateError which holds list of `client.rest.ApiException`
        instances for each object that failed to create.
    """
    with open(path.abspath(yaml_file)) as f:
        yml_document_all = yaml.safe_load_all(f)

        failures = []
        for yml_document in yml_document_all:
            try:
                create_from_dict(k8s_client, yml_document, verbose,
                                 namespace=namespace,
                                 **kwargs)
            except FailToCreateError as failure:
                failures.extend(failure.api_exceptions)
        if failures:
            raise FailToCreateError(failures)


def create_from_dict(k8s_client, data, verbose=False, namespace='default',
                     wait_until_ready=False, **kwargs):
    """
    Perform an action from a dictionary containing valid kubernetes
    API object (i.e. List, Service, etc).
    Input:
    k8s_client: an ApiClient object, initialized with the client args.
    data: a dictionary holding valid kubernetes objects
    verbose: If True, print confirmation from the create action.
        Default is False.
    namespace: string. Contains the namespace to create all
        resources inside. The namespace must preexist otherwise
        the resource creation will fail. If the API object in
        the yaml file already contains a namespace definition
        this parameter has no effect.
    Raises:
        FailToCreateError which holds list of `client.rest.ApiException`
        instances for each object that failed to create.
    """
    # Ensure the threads are cleaned up promptly
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # If it is a list type, will need to iterate its items
        api_exceptions = []
        # List of futures for all resources when they become ready
        futures_dict_resources_ready = {}

        if "List" in data["kind"]:
            # Could be "List" or "Pod/Service/...List"
            # This is a list type. iterate within its items
            kind = data["kind"].replace("List", "")
            for yml_object in data["items"]:
                # Mitigate cases when server returns a xxxList object
                # See kubernetes-client/python#586
                if kind is not "":
                    yml_object["apiVersion"] = data["apiVersion"]
                    yml_object["kind"] = kind
                try:
                    future_resource_ready = create_from_yaml_single_item(
                        k8s_client, yml_object, executor, verbose, namespace=namespace,
                        **kwargs)
                    # add resource ready future to the dict
                    futures_dict_resources_ready[future_resource_ready] = yml_object
                except client.rest.ApiException as api_exception:
                    api_exceptions.append(api_exception)
        else:
            # This is a single object. Call the single item method
            try:
                future_resource_ready = create_from_yaml_single_item(
                    k8s_client, data, executor, verbose, namespace=namespace, **kwargs)
                    # add resource ready future to the dict
                futures_dict_resources_ready[future_resource_ready] = data
            except client.rest.ApiException as api_exception:
                api_exceptions.append(api_exception)

        # In case we have exceptions waiting for us, raise them
        if api_exceptions:
            raise FailToCreateError(api_exceptions)

        if wait_until_ready:
            # wait for all futures
            for future in concurrent.futures.as_completed(futures_dict_resources_ready, timeout=60):
                yaml_object = futures_dict_resources_ready[future]
                try:
                    data = future.result()
                    # print yaml object and its future's result
                    print(yaml_object, data)
                except Exception as exc:
                    print('%s generated an exception: %s' % (yaml_object, exc))
                else:
                    print('%s is ready: %b' % (yaml_object, data))
            print("All resources are ready!")


def resource_is_ready(k8s_api, kind, resource_name, kwargs):
    # assert that namespaceless resources are instantly ready
    if kwargs["namespace"] is None:
        return True
    while True:
      response = getattr(k8s_api, "read_namespaced_{0}".format(kind))(name=resource_name, **kwargs)
      response_dict = response.to_dict()
      status_dict = response_dict.get("status", "Ready")
      if kind == "deployment":
          print("waiting for deployment")
          if status_dict["ready_replicas"] and status_dict["replicas"] == status_dict["ready_replicas"]:
              print("Deployment is ready")
              return True
      elif kind == "pod":
          print("waiting for pod")
          if status_dict["phase"] == "Running":
              print("Pod is ready")
              return True
      else:
          print("kind not supported:", kind, response_dict)
          return False
      # sleep for a second to save CPU load
      time.sleep(1)

def create_from_yaml_single_item(
        k8s_client, yml_object, executor, verbose=False, **kwargs):
    group, _, version = yml_object["apiVersion"].partition("/")
    if version == "":
        version = group
        group = "core"
    # Take care for the case e.g. api_type is "apiextensions.k8s.io"
    # Only replace the last instance
    group = "".join(group.rsplit(".k8s.io", 1))
    # convert group name from DNS subdomain format to
    # python class name convention
    group = "".join(word.capitalize() for word in group.split('.'))
    fcn_to_call = "{0}{1}Api".format(group, version.capitalize())
    k8s_api = getattr(client, fcn_to_call)(k8s_client)
    # Replace CamelCased action_type into snake_case
    kind = yml_object["kind"]
    kind = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', kind)
    kind = re.sub('([a-z0-9])([A-Z])', r'\1_\2', kind).lower()
    resource_name = yml_object["metadata"]["name"]
    # Expect the user to create namespaced objects more often
    if hasattr(k8s_api, "create_namespaced_{0}".format(kind)):
        # Decide which namespace we are going to put the object in,
        # if any
        if "namespace" in yml_object["metadata"]:
            namespace = yml_object["metadata"]["namespace"]
            kwargs['namespace'] = namespace
        resp = getattr(k8s_api, "create_namespaced_{0}".format(kind))(
            body=yml_object, **kwargs)
    else:
        # resource is namespaceless (and also instantly ready)
        kwargs.pop('namespace', None)
        resp = getattr(k8s_api, "create_{0}".format(kind))(
            body=yml_object, **kwargs)
    if verbose:
        msg = "{0} created.".format(kind)
        if hasattr(resp, 'status'):
            msg += " status='{0}'".format(str(resp.status))
        print(msg)

    # future that returns True when the resource becomes ready
    return executor.submit(resource_is_ready, k8s_api, kind, resource_name, kwargs, 60)
