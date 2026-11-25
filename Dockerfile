# 离线可运行镜像：构建期安装依赖，运行期不访问网络（docker run --network none 可跑通）
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

COPY --from=builder /install /usr/local
WORKDIR /app
COPY cal ./cal
COPY cal.yaml ./
COPY golden ./golden
COPY data/raw ./data/raw
COPY scripts ./scripts
COPY bin/cal /usr/local/bin/cal
RUN chmod 0755 /usr/local/bin/cal \
    && useradd --create-home --uid 10001 cal \
    && mkdir -p /app/runs \
    && chown -R cal:cal /app

USER cal
ENTRYPOINT ["cal"]
CMD ["run", "--config", "cal.yaml"]
