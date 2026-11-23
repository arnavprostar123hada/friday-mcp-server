
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y git ca-certificates \
    && git clone https://github.com/78/mcp-calculator.git /opt/xiaozhi-bridge \
    && git -C /opt/xiaozhi-bridge checkout c537f71d61fd73b47d6c8955b5df6d3721acf4e4 \
    && pip install --no-cache-dir -r /opt/xiaozhi-bridge/requirements.txt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY friday_tools.py /app/friday_tools.py

CMD ["python", "/opt/xiaozhi-bridge/mcp_pipe.py", "/app/friday_tools.py"]
