FROM python:3.8-slim-buster AS builder

RUN mkdir -p /src/app && \
    apt-get update && \
    apt-get install -y git wget nmap

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
FROM gcr.io/distroless/python3-debian10

# Install illuminatio from builder
COPY --from=builder /src/app/src /src/app/src
COPY --from=builder /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY --from=builder /usr/local/bin/illuminatio-runner /usr/local/bin/illuminatio-runner
COPY --from=builder /usr/local/bin/illuminatio /usr/local/bin/illuminatio
COPY --from=builder /usr/local/bin/crictl /usr/local/bin/crictl
# Install nmap for network testing
COPY --from=builder /usr/bin/nmap /usr/bin/nmap
COPY --from=builder /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libpcap.so.0.8 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libssh2.so.1 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/liblua5.3.so.0 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/liblinear.so.3 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libblas.so.3 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libgfortran.so.5 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libquadmath.so.0 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libgcrypt.so.20 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libpcre.so.3 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libgpg-error.so.0 /lib/x86_64-linux-gnu/
COPY --from=builder /usr/share/nmap /usr/share/nmap

ENV PYTHONPATH=/usr/local/lib/python3.8/site-packages

CMD [ "/usr/local/bin/illuminatio-runner" ]
