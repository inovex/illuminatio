"""
Contains several illuminatio constants especially names and some util functions
"""
from random import choice
from dataclasses import dataclass
from functools import partial
from typing import Callable, Any, IO, Optional
import os
import json
import sys
import yaml

PROJECT_PREFIX = "illuminatio"
PROJECT_NAMESPACE = PROJECT_PREFIX
CLEANUP_LABEL = "%s-cleanup" % PROJECT_PREFIX
ROLE_LABEL = "%s-role" % PROJECT_PREFIX
INVERTED_ATTRIBUTE_PREFIX = "%s-inverted-" % PROJECT_PREFIX

CLEANUP_ALWAYS = "always"
CLEANUP_ON_REQUEST = "on-request"

CLEANUP_VALUES = [CLEANUP_ALWAYS, CLEANUP_ON_REQUEST]

STD_IDENTIFIER = "-"


@dataclass(repr=False, frozen=True)
class Format:
    """
    A format able to load and dump data.
    """

    load: Callable[[IO[bytes]], Any]
    dump: Callable[[Any, IO[str]], None]


JSON = Format(json.load, partial(json.dump, indent=2))
YAML = Format(yaml.safe_load, partial(yaml.safe_dump, default_flow_style=False))

FORMATS = {
    "json": JSON,
    "yaml": YAML,
    "yml": YAML,
}


def open_or_std(file, std, *args, **kwargs):
    """
    Opens the file in the specified mode unless file is STD_IDENTIFIER,
    in which case it returns std.
    """
    if file == STD_IDENTIFIER:
        return std
    return open(file, *args, **kwargs)


def format_for(
    filename: Optional[str] = None, format_name: Optional[str] = None
) -> Format:
    """
    Obtains the format for the filename and optional explicit format name.

    If the explicit format name is omitted, the filename extension is used as format name.
    """
    if not format_name and filename:
        _, ext = os.path.splitext(filename)
        format_name = format_name or ext[1:]

    if format_name:
        fmt = FORMATS.get(format_name)
    else:
        fmt = JSON

    if not fmt:
        raise ValueError("Unknown format %s" % format_name)
    return fmt


def write_formatted(
    data: Any, filename: str, format_name: Optional[str] = None
) -> None:
    """
    Writes the data to the target file, inferring the format from the filename if not specified explicitly.
    """
    fmt = format_for(filename, format_name)

    with open_or_std(filename, sys.stdout, "w") as file:
        fmt.dump(data, file)


def read_formatted(filename: str, format_name: Optional[str] = None) -> Any:
    """
    Reads the data from the target file, inferring the format from the filename if not specified explicitly.
    """
    fmt = format_for(filename, format_name)

    with open_or_std(filename, sys.stdin, "r") as file:
        return fmt.load(file)


def validate_cleanup_in(labels):
    """
    Validates the presence of the CLEANUP_LABEL and its values in a list of labels, raises ValueError otherwise
    """
    if CLEANUP_LABEL not in labels:
        raise ValueError("Cleanup label (%s) missing in pod labels." % CLEANUP_LABEL)
    if labels[CLEANUP_LABEL] not in CLEANUP_VALUES:
        raise ValueError(
            "Cleanup value %s not permitted. Use one of: %s"
            % (labels[CLEANUP_LABEL], CLEANUP_VALUES)
        )


def rand_port(except_ports=None):
    """
    Returns a random port, exclusions possible via parameter set
    """
    if except_ports is None:
        except_ports = []
    max_port_int = 65535
    if len(set(except_ports)) > max_port_int >= max(except_ports):
        raise ValueError(
            "Cannot generate randomPort when all possible port numbers are exempt"
        )
    # choose random port from all ports except exceptPorts
    return choice(
        [port for port in range(max_port_int + 1) if port not in except_ports]
    )


def add_illuminatio_labels(labels: dict) -> dict:
    if labels is None or len(labels) == 0:
        labels = {}

    labels[CLEANUP_LABEL] = CLEANUP_ON_REQUEST

    return labels
