ARG BUILD_FROM=hassioaddons/base-python:4.0.0

# hadolint ignore=DL3006
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG C.UTF-8

# Copy data for add-on
COPY requirements.txt /tmp/

# Install requirements for add-on
RUN \
    apk add --no-cache --virtual .build-dependencies \
      gcc=9.2.0-r3 \
      musl-dev=1.1.24-r0 \
    && pip install -r /tmp/requirements.txt \
    && apk del --purge .build-dependencies


COPY rootfs /
#WORKDIR /data

CMD python /app.py