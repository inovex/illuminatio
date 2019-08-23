# latest base image without vulnerabilities
FROM python:3.5.7-alpine3.10

COPY . /illuminatio
COPY .git /illuminatio/.git

WORKDIR /illuminatio

RUN apk add git && pip install .

CMD ["/bin/sh"]
