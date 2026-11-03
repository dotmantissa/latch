FROM mcr.microsoft.com/playwright/python:v1.64.1-noble@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031

LABEL latch.playwright.version="1.64.1"
LABEL latch.purpose="p0-browser-spike"
COPY infra/browser/requirements.lock /opt/latch/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/latch/requirements.lock
COPY services/supervisor/browser_probe.py /opt/latch/browser_probe.py
USER 1000:1000
ENV HOME=/tmp/latch-home
WORKDIR /tmp
ENTRYPOINT ["python", "/opt/latch/browser_probe.py"]
