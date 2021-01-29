import pytest
import kubernetes

from illuminatio.k8s_util import resolve_port_from_candidates, is_numerical_port


@pytest.mark.parametrize(
    "pods,portname,expected_port",
    [
        (
            kubernetes.client.V1PodList(
                api_version="v1",
                items=[
                    kubernetes.client.V1Pod(
                        spec=kubernetes.client.V1PodSpec(
                            containers=[
                                kubernetes.client.V1Container(
                                    image="nginx",
                                    name="myfancydeployment",
                                    ports=[
                                        kubernetes.client.V1ContainerPort(
                                            name="mywronlgynamedport",
                                            container_port=8080,
                                            protocol="TCP",
                                        ),
                                        kubernetes.client.V1ContainerPort(
                                            name="mynamedport",
                                            container_port=80,
                                            protocol="TCP",
                                        ),
                                    ],
                                )
                            ]
                        )
                    )
                ],
            ),
            "mynamedport",
            80,
        ),
    ],
)
def test_resolve_port_from_candidates(pods, portname, expected_port):
    actual_port = resolve_port_from_candidates(pods, portname)
    assert actual_port == expected_port


@pytest.mark.parametrize(
    "port,expected", [("80", True), ("*", False), (80, True), ("my-named-port", False)],
)
def test_is_numerical_port(port, expected):
    actual = is_numerical_port(port)
    assert actual == expected
