# EchoMind 智能客服系统 — Docker 多阶段构建
# 目标：生产镜像尽量精简，开发镜像包含调试工具

# ── 阶段 1：基础环境 ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# curl 用于健康检查；不再需要 gcc/g++（已移除本地 ML 模型）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── 阶段 2：安装 Python 依赖 ──────────────────────────────────────────────────
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 文档解析与向量入库依赖仅安装在后台 Worker 镜像中。
FROM base AS rag-dependencies

COPY requirements.txt requirements-rag.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-rag.txt

# ── 阶段 3：生产镜像 ──────────────────────────────────────────────────────────
FROM base AS production

# 非 root 用户运行。先创建用户，后续 COPY 直接带 owner，避免 chown -R 复制出额外大层。
RUN useradd -m -u 1000 studypilot

# 从依赖阶段复制已安装的包
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin
# 复制应用代码
COPY --chown=studypilot:studypilot . .

# 创建必要目录，只调整运行期需要写入的目录权限，避免递归 chown 整个应用。
RUN mkdir -p /app/data/chroma /app/data/uploads /app/logs /app/config && \
    chown studypilot:studypilot /app/data /app/data/chroma /app/data/uploads /app/logs /app/config
USER studypilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── 阶段 4：文档入库 Worker ───────────────────────────────────────────────────
FROM base AS worker

RUN useradd -m -u 1000 studypilot

COPY --from=rag-dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=rag-dependencies /usr/local/bin /usr/local/bin
COPY --chown=studypilot:studypilot . .

RUN mkdir -p /app/data/uploads /app/logs && \
    chown studypilot:studypilot /app/data /app/data/uploads /app/logs
USER studypilot

CMD ["python", "-m", "app.tasks.worker"]

# ── 阶段 5：开发镜像 ──────────────────────────────────────────────────────────
FROM dependencies AS development

COPY . .

RUN mkdir -p /app/data/chroma /app/logs /app/config /app/tests && \
    chmod -R 777 /app/data /app/logs

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
