import pytest
import nmap
from unittest.mock import MagicMock
from illuminatio.illuminatio_runner import (
    build_result_string,
    extract_results_from_nmap,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            {
                "port": "TCP/80",
                "target": "test",
                "should_be_blocked": False,
                "was_blocked": False,
            },
            "Test test:TCP/80 succeeded\nCould reach test on port TCP/80. Expected target to be reachable",
        ),
        (
            {
                "port": "TCP/80",
                "target": "test",
                "should_be_blocked": False,
                "was_blocked": True,
            },
            "Test test:TCP/80 failed\nCouldn't reach test on port TCP/80. Expected target to be reachable",
        ),
        (
            {
                "port": "TCP/80",
                "target": "test",
                "should_be_blocked": True,
                "was_blocked": False,
            },
            "Test test:-TCP/80 failed\nCould reach test on port TCP/80. Expected target to not be reachable",
        ),
        (
            {
                "port": "TCP/80",
                "target": "test",
                "should_be_blocked": True,
                "was_blocked": True,
            },
            "Test test:-TCP/80 succeeded\nCouldn't reach test on port TCP/80. Expected target to not be reachable",
        ),
    ],
)
def test_build_result_string(test_input, expected):
    assert build_result_string(**test_input) == expected


def create_nmap_mock(hosts: list()):
    nmap_mock = nmap.PortScanner()
    nmap_mock.all_hosts = MagicMock(return_value=hosts)
    nmap_mock._scan_result = MagicMock(return_value={"scan"})
    if len(hosts) > 0:
        nmap_mock[hosts[0]].all_protocols = MagicMock(return_value=["tcp"])
        nmap_mock[hosts[0]]["tcp"].keys = MagicMock(return_value=[80])
        nmap_mock[hosts[0]].tcp = MagicMock(
            return_value={"state": "open", "reason": "syn-ack", "name": "http"}
        )

    return nmap_mock


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            {"hosts": [], "port_on_nums": {}, "target": "test"},
            {
                "": {
                    "error": "Found 0 hosts in nmap results, expected 1.",
                    "success": False,
                }
            },
        ),
        (
            {
                "hosts": ["123.321.123.321"],
                "port_on_nums": {"TCP/80": "TCP/80"},
                "target": "test",
            },
            {
                "TCP/80": {
                    "nmap-state": "open",
                    "string": "Test test:TCP/80 succeeded\n"
                    "Could reach test on port TCP/80. Expected target to be "
                    "reachable",
                    "success": True,
                }
            },
        ),
        (
            {
                "hosts": ["123.321.123.321"],
                "port_on_nums": {"TCP/80": "-TCP/80"},
                "target": "test",
            },
            {
                "-TCP/80": {
                    "nmap-state": "open",
                    "string": "Test test:-TCP/80 failed\n"
                    "Could reach test on port TCP/80. Expected target to not be "
                    "reachable",
                    "success": False,
                }
            },
        ),
        (
            {"hosts": ["::1"], "port_on_nums": {"TCP/80": "-TCP/80"}, "target": "test"},
            {
                "-TCP/80": {
                    "nmap-state": "open",
                    "string": "Test test:-TCP/80 failed\n"
                    "Could reach test on port TCP/80. Expected target to not be "
                    "reachable",
                    "success": False,
                }
            },
        ),
    ],
)
def test_extract_results_from_nmap(test_input, expected):
    test_input["nmap_res"] = create_nmap_mock(test_input["hosts"])
    test_input.pop("hosts", None)
    assert extract_results_from_nmap(**test_input) == expected
