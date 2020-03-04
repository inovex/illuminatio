#!/usr/bin/env bash

# Abort if any of the following commands fails or variables are undefined
set -eu

python setup.py test --addopts="-m e2e"
