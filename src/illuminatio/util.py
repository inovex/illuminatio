from random import choice

PROJECT_PREFIX = "illuminatio"
DAEMONSET_NAME = PROJECT_PREFIX + "-runner"
PROJECT_NAMESPACE = PROJECT_PREFIX
CLEANUP_LABEL = PROJECT_PREFIX + "-cleanup"
ROLE_LABEL = PROJECT_PREFIX + "-role"
INVERTED_ATTRIBUTE_PREFIX = PROJECT_PREFIX + "-inverted-"

CLEANUP_ALWAYS = "always"
CLEANUP_ON_REQUEST = "on-request"

cleanup_values = [CLEANUP_ALWAYS, CLEANUP_ON_REQUEST]


def validate_cleanup_in(labels):
    if CLEANUP_LABEL not in labels:
        raise ValueError("Cleanup label (" + CLEANUP_LABEL + ") missing in pod labels.")
    elif labels[CLEANUP_LABEL] not in cleanup_values:
        raise ValueError("Cleanup value " + labels[CLEANUP_LABEL]
                         + " not permitted. Use one of: " + str(cleanup_values))


def rand_port(except_ports=None):
    if except_ports is None:
        except_ports = []
    max_port_int = 65535
    if len(set(except_ports)) > max_port_int >= max(except_ports):
        raise ValueError("Cannot generate randomPort when all possible port numbers are exempt")
    # choose random port from all ports except exceptPorts
    return choice([port for port in range(max_port_int + 1) if port not in except_ports])
