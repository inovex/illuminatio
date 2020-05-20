import pytest
from illuminatio.util import (
    rand_port,
    add_illuminatio_labels,
    CLEANUP_LABEL,
    CLEANUP_ON_REQUEST,
)


def test_randPort_noExceptPorts_returnsInt():
    assert isinstance(rand_port(), int)


def test_randPort_allPortsExcept_raisesException():
    with pytest.raises(Exception):
        rand_port(except_ports=list(range(65535 + 1)))


@pytest.mark.slow
def test_randPort_allButOnePortsExcepted_returnsRemainingPort():
    generated = rand_port(except_ports=list(range(65535)))
    assert generated == 65535


# from illuminatio.util import INVERTED_ATTRIBUTE_PREFIX
@pytest.mark.parametrize(
    "test_input,expected",
    [
        (None, {CLEANUP_LABEL: CLEANUP_ON_REQUEST}),
        ({}, {CLEANUP_LABEL: CLEANUP_ON_REQUEST}),
        ({"test": "test"}, {"test": "test", CLEANUP_LABEL: CLEANUP_ON_REQUEST}),
    ],
)
def test_add_illuminatio_labels(test_input, expected):
    assert add_illuminatio_labels(test_input) == expected
