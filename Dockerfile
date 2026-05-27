FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
COPY knowledge_base/ knowledge_base/
COPY system_prompt.md .
EXPOSE 7860
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "7860"]
