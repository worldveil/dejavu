FROM python:3.7
RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install \
    gcc nano \
    ffmpeg libasound-dev portaudio19-dev libportaudio2 libportaudiocpp0 \
    postgresql postgresql-contrib -y
RUN pip install numpy scipy matplotlib pydub pyaudio psycopg2
WORKDIR /code