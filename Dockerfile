FROM python:3.9.6

WORKDIR /code

COPY spot_lib_mng spot_lib_mng
COPY requirements.txt .
COPY run_api.sh .
COPY spotify_playlist_ids.csv .
COPY .env .

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

EXPOSE 8080

CMD ["uvicorn", "spot_lib_mng.api:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8080"]