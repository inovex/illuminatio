FROM python:3.7.4-alpine3.10 AS builder

COPY . /illuminatio
COPY .git /illuminatio/.git

WORKDIR /illuminatio

RUN apk add --no-cache git && \
    adduser -S illuminatio  -s /bin/nologin -u 1000 && \
    chmod 1777 /tmp

RUN pip install --no-warn-script-location --user . && \
    chown -R illuminatio /root/.local

# Final image
FROM python:3.7.4-alpine3.10

RUN adduser -S illuminatio -H -s /bin/nologin -u 1000
USER 1000

COPY --from=builder /root/.local /home/illuminatio/.local
ENV PATH=/home/illuminatio/.local/bin:$PATH

ENTRYPOINT [ "illuminatio" ]
