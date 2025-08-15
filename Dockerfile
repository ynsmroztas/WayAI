FROM python:3.12-slim
WORKDIR /app
COPY webgui/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY webgui /app
EXPOSE 8080
CMD ["python","app.py"]
