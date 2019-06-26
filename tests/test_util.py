import pytest
from illuminatio.util import rand_port


def test_randPort_noExceptPorts_returnsInt():
    assert isinstance(rand_port(), int)


def test_randPort_allPortsExcept_raisesException():
    with pytest.raises(Exception):
        rand_port(except_ports=list(range(65535 + 1)))


@pytest.mark.slow
def test_randPort_allButOnePortsExcepted_returnsRemainingPort():
    generated = rand_port(except_ports=list(range(65535)))
    assert generated == 65535
