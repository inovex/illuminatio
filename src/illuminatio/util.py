"""
Contains several illuminatio constants especially names and some util functions
"""
from random import choice

PROJECT_PREFIX = "illuminatio"
PROJECT_NAMESPACE = PROJECT_PREFIX
CLEANUP_LABEL = "%s-cleanup" % PROJECT_PREFIX
ROLE_LABEL = "%s-role" % PROJECT_PREFIX
INVERTED_ATTRIBUTE_PREFIX = "%s-inverted-" % PROJECT_PREFIX

CLEANUP_ALWAYS = "always"
CLEANUP_ON_REQUEST = "on-request"

CLEANUP_VALUES = [CLEANUP_ALWAYS, CLEANUP_ON_REQUEST]


def validate_cleanup_in(labels):
    """
    Validates the presence of the CLEANUP_LABEL and its values in a list of labels, raises ValueError otherwise
    """
    if CLEANUP_LABEL not in labels:
        raise ValueError("Cleanup label (%s) missing in pod labels." % CLEANUP_LABEL)
    if labels[CLEANUP_LABEL] not in CLEANUP_VALUES:
        raise ValueError("Cleanup value %s not permitted. Use one of: %s" % (
            labels[CLEANUP_LABEL], CLEANUP_VALUES))


def rand_port(except_ports=None):
    """
    Returns a random port, exclusions possible via parameter set
    """
    if except_ports is None:
        except_ports = []
    max_port_int = 65535
    if len(set(except_ports)) > max_port_int >= max(except_ports):
        raise ValueError("Cannot generate randomPort when all possible port numbers are exempt")
    # choose random port from all ports except exceptPorts
    return choice([port for port in range(max_port_int + 1) if port not in except_ports])
