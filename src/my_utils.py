import ffmpeg
import numpy as np
import logging
import os


def load_audio(file, sr):
    logger = logging.getLogger(__name__)

    try:
        logger.debug(f"Starting load_audio with parameters:")
        logger.debug(f"Input file: {file}")
        logger.debug(f"Sample rate: {sr}")

        # 파일 경로 전처리
        file = file.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        logger.debug(f"Cleaned file path: {file}")

        # 파일 존재 여부 확인
        logger.debug(f"Checking file existence")
        if not os.path.exists(file):
            logger.error(f"File not found: {file}")
            raise FileNotFoundError(f"File not found: {file}")
        logger.debug(f"File exists. Size: {os.path.getsize(file)} bytes")
        logger.debug(f"Absolute path: {os.path.abspath(file)}")

        # ffmpeg 명령어 구성
        logger.debug("Constructing ffmpeg command")
        ffmpeg_command = ffmpeg.input(file, threads=0).output(
            "-", format="f32le", acodec="pcm_f32le", ac=1, ar=sr
        )
        logger.debug(f"FFmpeg command: {' '.join(ffmpeg_command.compile())}")

        # ffmpeg 실행
        logger.debug("Executing ffmpeg command")
        try:
            out, stderr = ffmpeg_command.run(
                cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True
            )
            logger.debug("FFmpeg command executed successfully")
            if stderr:
                logger.debug(
                    f"FFmpeg stderr output: {stderr.decode() if isinstance(stderr, bytes) else stderr}"
                )

        except ffmpeg.Error as e:
            logger.error("FFmpeg error occurred")
            logger.error(f"FFmpeg stdout: {e.stdout.decode() if e.stdout else 'None'}")
            logger.error(f"FFmpeg stderr: {e.stderr.decode() if e.stderr else 'None'}")
            raise RuntimeError(f"FFmpeg error (see stderr output for detail)")

        except Exception as e:
            logger.error(f"Unexpected error during ffmpeg execution: {str(e)}")
            raise

        # numpy 변환
        logger.debug("Converting output to numpy array")
        try:
            audio_data = np.frombuffer(out, np.float32).flatten()
            logger.debug(f"Audio data shape: {audio_data.shape}")
            return audio_data

        except Exception as e:
            logger.error(f"Error converting output to numpy array: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"Failed to load audio: {str(e)}")
        raise RuntimeError(f"Failed to load audio: {e}")
