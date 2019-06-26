FROM python:3.7-alpine AS builder

RUN apk add --no-cache git alpine-sdk libffi-dev openssl-dev python3-dev && \
    mkdir -p /wheels

WORKDIR /wheels
COPY ./requirements.txt /wheels/requirements.txt
RUN pip3 wheel -r ./requirements.txt

# Actual Runner image
FROM python:3.7-alpine

COPY --from=builder /wheels /wheels

# ToDo remove the need for nmap
# Currently git is req. for local pip
RUN apk add --no-cache nmap git && \
    mkdir -p /src/app && \
    adduser -S -D -H runner

ENV CRICTL_VERSION="v1.13.0"
RUN wget https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz && \
    tar zxvf crictl-${CRICTL_VERSION}-linux-amd64.tar.gz -C /usr/local/bin && \
    rm -f crictl-${CRICTL_VERSION}-linux-amd64.tar.gz

COPY Makefile /src/app/.
COPY requirements.txt /src/app/.
COPY setup.cfg /src/app/.
COPY setup.py /src/app/.
COPY .git /src/app/.git
COPY src/illuminatio/__init__.py /src/app/src/illuminatio/__init__.py
WORKDIR /src/app

RUN pip3 --no-cache-dir install -e . -r requirements.txt -f /wheels && \
    rm -rf /wheels && \
    rm -rf .git && \
    apk del --purge --no-cache git

COPY src /src/app/src

USER runner

ENTRYPOINT [ "illuminatio_runner" ]