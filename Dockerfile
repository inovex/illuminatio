FROM python:3.8-slim-buster AS builder

RUN mkdir -p /src/app && \
    apt-get update && \
    apt-get install -y git wget

ENV CRICTL_VERSION="v1.18.0"
RUN wget https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz && \
    tar zxvf crictl-${CRICTL_VERSION}-linux-amd64.tar.gz -C /usr/local/bin && \
    rm -f crictl-${CRICTL_VERSION}-linux-amd64.tar.gz

COPY setup.cfg /src/app
COPY setup.py /src/app
COPY .git /src/app/.git
COPY src /src/app/src
COPY ./requirements.txt /src/app/requirements.txt

WORKDIR /src/app
RUN pip3 --no-cache-dir install . -r ./requirements.txt

# Actual Runner image
FROM python:3.8-slim-buster

# Install illuminatio from builder
COPY --from=builder /src/app/src /src/app/src
COPY --from=builder /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY --from=builder /usr/local/bin/illuminatio-runner /usr/local/bin/illuminatio-runner
COPY --from=builder /usr/local/bin/illuminatio /usr/local/bin/illuminatio
COPY --from=builder /usr/local/bin/crictl /usr/local/bin/crictl

ENV PYTHONPATH=/usr/local/lib/python3.8/site-packages
# Home directory of root user is not recognized when using ~ (default: ~/.kube/config)
ENV KUBECONFIG=/kubeconfig

# Currently nmap is required for running the scans
RUN apt-get update && \
    apt-get install -y nmap && \
    rm -rf /var/lib/apt/lists/*

CMD [ "/usr/local/bin/illuminatio-runner" ]
