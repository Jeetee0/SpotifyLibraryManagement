FROM python:3.9.6
WORKDIR /python-backend
COPY spot_lib_mng spot_lib_mng
COPY requirements.txt .
COPY run_api.sh .
COPY spotify_playlist_ids.csv .
COPY .env .

EXPOSE 9090

CMD ["./run_api.sh"]