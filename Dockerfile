FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
ENV TEST_INPUTS_PATH=/workspace/test_inputs.json
ENV RESULTS_PATH=/workspace/results.json
CMD ["python", "agent.py"]
