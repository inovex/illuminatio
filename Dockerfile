# latest base image without vulnerabilities
FROM python:3.7.4-alpine3.10

COPY . /illuminatio
COPY .git /illuminatio/.git

WORKDIR /illuminatio

RUN apk add git && pip install .

CMD ["/bin/sh"]
