# epub2m4b — minimal image. ffmpeg is provided by the base distro packages.
# Chinese text needs no extra fonts: the tool never renders text.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOUNDBOOK_HOME=/data/state \
    SOUNDBOOK_CACHE_DIR=/data/cache

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# PyPI can be slow/unreachable from some networks; override at build time:
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple .
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TIMEOUT=120

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --index-url "$PIP_INDEX_URL" --timeout "$PIP_TIMEOUT" --retries 5 . \
 && rm -rf /app/src

VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["epub2m4b"]
CMD ["--help"]
