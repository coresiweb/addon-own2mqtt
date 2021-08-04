ARG BUILD_FROM=ghcr.io/hassio-addons/base-python/amd64:7.1.0

# hadolint ignore=DL3006
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG C.UTF-8

# Copy data for add-on
COPY requirements.txt /tmp/

# Install requirements for add-on
RUN \
    apk add --no-cache --virtual .build-dependencies \
      gcc=10.3.1_git20210424-r2 \
      musl-dev=1.2.2-r3	 \
    && pip install -r /tmp/requirements.txt \
    && apk del --purge .build-dependencies


COPY rootfs /
#WORKDIR /data

CMD python /app.py