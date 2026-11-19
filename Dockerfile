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

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && rm -rf /app/src

VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["epub2m4b"]
CMD ["--help"]
