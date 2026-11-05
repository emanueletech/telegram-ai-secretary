FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# nodejs/npm used to be installed here to provide the Claude Code CLI, but
# claude-agent-sdk ships its own native binary in claude_agent_sdk/_bundled/
# and the logs show that is the one actually executed — the npm copy was dead
# weight (~300 MB and a slow, unpinned install on every rebuild).
# libgomp1 is required by ctranslate2 (faster-whisper).
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Rome

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt
# The bundled CLI is the only Claude Code binary in the image now, so fail the
# BUILD loudly if this architecture's wheel doesn't carry it, rather than
# shipping an image whose AI replies die at runtime.
RUN pip install -r /app/requirements.txt \
    && python -c "import pathlib, claude_agent_sdk as s; \
p = pathlib.Path(s.__file__).parent / '_bundled' / 'claude'; \
assert p.exists(), 'bundled Claude Code CLI missing for this architecture'; \
print('bundled Claude Code CLI OK:', p, p.stat().st_size // 1048576, 'MB')"

COPY app /app
# Extensions dropped into app/extensions/ (e.g. by a deploy overlay) may bring
# their own requirements.txt; install it when present.
RUN if [ -f /app/extensions/requirements.txt ]; then \
        pip install -r /app/extensions/requirements.txt; \
    fi

# Non-root user: claude-code CLI refuses --dangerously-skip-permissions
# when running as root. UID/GID 1000 typically matches the host user on NAS appliances.
RUN useradd -m -u 1000 -s /bin/bash bot \
    && mkdir -p /app/data /home/bot/.claude \
    && chown -R bot:bot /app /home/bot
USER bot
ENV HOME=/home/bot

HEALTHCHECK --interval=2m --timeout=10s --start-period=1m --retries=3 \
    CMD python -c "import os,sys,time; p='/app/data/health.txt'; \
sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<300 else 1)"

CMD ["python", "-u", "bot.py"]
