import pytest

from illuminatio.host import (
    ClusterHost,
    ConcreteClusterHost,
    ExternalHost,
    LocalHost,
    GenericClusterHost,
    Host,
)


@pytest.mark.parametrize(
    "identifier,expected_host",
    [
        pytest.param("localhost", LocalHost(), id="LocalHost"),
        pytest.param(
            "127.0.0.1",
            ExternalHost("127.0.0.1"),
            id="ExternalHost with localhost IPv4",
        ),
        pytest.param(
            "123.123.123.123",
            ExternalHost("123.123.123.123"),
            id="ExternalHost with IPv4",
        ),
        pytest.param(
            "fe80::1ff:fe23:4567:890a",
            ExternalHost("fe80::1ff:fe23:4567:890a"),
            id="ExternalHost with IPv6",
        ),
        pytest.param(
            "default:nginx-23429-asdf",
            ConcreteClusterHost("default", "nginx-23429-asdf"),
            id="Simple ConcreteClusterHost",
        ),
        pytest.param(
            "default:test=test",
            ClusterHost("default", {"test": "test"}),
            id="Simple ClusterHost",
        ),
        pytest.param(
            "illuminatio-inverted-default:illuminatio-inverted-test.io/test-123_XYZ=test_456-123.ABC",
            ClusterHost(
                "illuminatio-inverted-default",
                {"illuminatio-inverted-test.io/test-123_XYZ": "test_456-123.ABC"},
            ),
            id="ClusterHost containing all allowed label characters",
        ),
        pytest.param(
            "test=test:test=test",
            GenericClusterHost({"test": "test"}, {"test": "test"}),
            id="Simple GenericClusterHost",
        ),
        pytest.param(
            "illuminatio-inverted-test.io/test-123_XYZ=test_456-123.ABC:"
            + "illuminatio-inverted-test.io/test-123_XYZ=test_456-123.ABC",
            GenericClusterHost(
                {"illuminatio-inverted-test.io/test-123_XYZ": "test_456-123.ABC"},
                {"illuminatio-inverted-test.io/test-123_XYZ": "test_456-123.ABC"},
            ),
            id="GenericClusterHost containing all allowed label characters",
        ),
    ],
)
def test_from_identifier(identifier, expected_host):
    host = Host.from_identifier(identifier)
    assert host == expected_host


@pytest.mark.parametrize("identifier", ["invalidHost", "123.456.789.148"])
def test_from_identifier_invalid_hosts(identifier):
    with pytest.raises(ValueError):
        Host.from_identifier(identifier)
