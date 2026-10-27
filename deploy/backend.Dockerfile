FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
ENV BLOCKCHAIN_MODE=embedded
EXPOSE 8000
# ONE worker: the embedded chain lives inside the process. With BLOCKCHAIN_MODE=rpc you may add workers.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
