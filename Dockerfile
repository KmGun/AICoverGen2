# NVIDIA CUDA 12.2 이미지 사용
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# NVIDIA Container Toolkit 설정
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# 사용자 기반 설치 경로 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUSERBASE /usr/local/python-packages
ENV PYTHONPATH /usr/local/python-packages/lib/python3.10/site-packages:$PYTHONPATH

# NVIDIA 드라이버 및 필수 패키지 설치
RUN apt-get update && \
   apt-get install -y --no-install-recommends \
   nvidia-driver-525-server \
   software-properties-common \
   wget build-essential libssl-dev zlib1g-dev \
   libncurses5-dev libncursesw5-dev libreadline-dev \
   libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev \
   libexpat1-dev liblzma-dev tk-dev tar libffi-dev && \
   wget https://www.python.org/ftp/python/3.10.2/Python-3.10.2.tgz && \
   tar -xzf Python-3.10.2.tgz && \
   cd Python-3.10.2 && \
   ./configure --enable-optimizations --with-system-ffi && \
   make -j$(nproc) && \
   make altinstall && \
   cd .. && rm -rf Python-3.10.2 Python-3.10.2.tgz

# 기본 python 및 pip 명령어를 Python 3.10에 연결
RUN ln -sf /usr/local/bin/python3.10 /usr/bin/python && \
   ln -sf /usr/local/bin/pip3.10 /usr/bin/pip

# 환경 변수 설정
ENV LD_LIBRARY_PATH="/usr/local/onnxruntime/lib:$LD_LIBRARY_PATH"
ENV PATH="/usr/local/onnxruntime/bin:$PATH"

# pip 업그레이드
RUN pip install --upgrade pip==23.1.2 --user

# 필수 패키지 설치
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt --user

# SOX 및 MP3 지원 패키지 설치
RUN apt-get update && \
   apt-get install -y sox libsox-fmt-mp3

# ffmpeg 및 관련 라이브러리 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libavcodec-extra \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavfilter-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libpostproc-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 루트 디렉토리의 모든 파일을 Docker 이미지에 복사
COPY . /app

# 모델 다운로드 스크립트 실행
RUN python /app/src/download_models.py

# 컨테이너 실행 시 execute.py 실행
CMD ["python", "/app/src/execute.py"]