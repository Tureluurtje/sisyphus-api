FROM python:3.13.0

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
COPY api ./api
COPY asgi_app.py ./

RUN pip install --no-cache-dir --upgrade pip \
	&& pip install --no-cache-dir -r requirements.txt

EXPOSE 9000

CMD ["uvicorn", "api.asgi_app:app", "--host", "0.0.0.0", "--port", "9000"]
