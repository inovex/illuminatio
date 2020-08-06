import pytest
import sys
import json
from illuminatio.util import (
    rand_port,
    add_illuminatio_labels,
    format_for,
    open_or_std,
    write_formatted,
    read_formatted,
    CLEANUP_LABEL,
    CLEANUP_ON_REQUEST,
    STD_IDENTIFIER,
    YAML,
    JSON,
)


@pytest.mark.parametrize(
    "filename,format_name,expected",
    [
        ("foo.yaml", None, YAML),
        ("foo.yml", None, YAML),
        ("foo.json", None, JSON),
        ("foo", None, JSON),
        ("foo.yaml", "yaml", YAML),
        ("foo.yaml", "json", JSON),
        (None, "yaml", YAML),
        (None, None, JSON),
    ],
)
def test_format_for(filename, format_name, expected):
    assert format_for(filename, format_name) == expected


def test_randPort_noExceptPorts_returnsInt():
    assert isinstance(rand_port(), int)


def test_randPort_allPortsExcept_raisesException():
    with pytest.raises(Exception):
        rand_port(except_ports=list(range(65535 + 1)))


def test_open_or_std(tmp_path):
    assert open_or_std(STD_IDENTIFIER, sys.stdin) is sys.stdin
    foo_file = tmp_path / "foo"
    foo_file.write_text("bar")
    with open_or_std(foo_file, None) as f1, open(foo_file) as f2:
        assert f1.read() == f2.read()


def test_write_formatted(tmp_path):
    test_file = tmp_path / "test.json"
    write_formatted({"foo": "bar"}, test_file)
    assert test_file.read_text() == json.dumps({"foo": "bar"}, indent=2)


def test_read_formatted(tmp_path):
    test_file = tmp_path / "test.json"
    test_file.write_text(r'{"foo":"bar"}')
    assert read_formatted(test_file) == {"foo": "bar"}


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
