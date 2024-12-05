import boto3
import json
import time
import subprocess
import os
import logging
import shutil
import sys
from typing import Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from infer import infer_ai_cover
import requests
import os
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class InferenceError(Exception):
    """추론 과정에서 발생하는 커스텀 예외"""

    pass


class SQSProcessor:
    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            region_name="ap-northeast-2",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.sqs = boto3.client(
            "sqs",
            region_name="ap-northeast-2",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.bucket_name = "song-request-bucket-1"
        self.queue_url = os.getenv("SQS_QUEUE_URL")  # SQS 큐 URL 환경변수 추가
        self.receipt_handle = os.getenv(
            "SQS_RECEIPT_HANDLE"
        )  # 메시지 receipt handle 환경변수 추가

        self.pitch_values_by_model = {
            "ljb": [-1, 0, 1],
            "ssk": [-2, -1],
            "ssh": [0, 1],
        }

        try:
            self.request_data = {
                "requestId": os.environ["REQUEST_ID"],
                "requestUserId": os.environ["REQUEST_USER_ID"],
                "modelName": os.environ["MODEL_NAME"],
                "isMaleSinger": os.environ["IS_MALE_SINGER"].lower() == "true",
                "model": os.environ["MODEL"],
                "guideName": os.environ["GUIDE_NAME"],
                "guideId": os.environ["GUIDE_ID"],
                "requestAt": os.environ["REQUEST_AT"],
            }
        except KeyError as e:
            logger.error(f"Missing required environment variable: {e}")
            sys.exit(1)

    def delete_sqs_message(self) -> bool:
        """SQS 메시지를 삭제합니다."""
        try:
            if not self.queue_url or not self.receipt_handle:
                logger.error("Missing SQS queue URL or receipt handle")
                return False

            self.sqs.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=self.receipt_handle
            )
            logger.info(f"SQS 메세지 삭제 완료: {self.request_data['requestId']}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete SQS message: {e}")
            return False

    def upload_folder_to_s3(self, input_dir: str, save_s3_dir: str):
        try:
            for root, _, files in os.walk(input_dir):
                logger.info(f"Scanning directory: {root}, Found files: {files}")
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    s3_path = os.path.join(
                        save_s3_dir, os.path.relpath(file_path, input_dir)
                    )

                    try:
                        self.s3.upload_file(file_path, self.bucket_name, s3_path)
                        logger.info(f"Uploaded {file_path} to {s3_path}")
                    except Exception as e:
                        logger.error(f"Failed to upload {file_path}: {e}")
                        raise

        except Exception as e:
            logger.error(f"Error in upload_folder_to_s3: {e}")
            raise

    def process_song_request(self) -> bool:
        """신청곡 데이터를 처리하고 추론을 실행합니다."""
        try:
            song_data = {
                "request_id": self.request_data["requestId"],
                "request_user_id": self.request_data["requestUserId"],
                "song_title": self.request_data["guideName"],
                "guide_id": self.request_data["guideId"],
                "voice_model": self.request_data["model"],
                "isMan": self.request_data["isMaleSinger"],
                "request_at": self.request_data["requestAt"],
            }

            try:
                result_folder_dir, song_uris = infer_ai_cover(
                    song_data["request_id"],
                    song_data["request_user_id"],
                    song_data["song_title"],
                    song_data["guide_id"],
                    song_data["voice_model"],
                    song_data["isMan"],
                )

                logger.info(
                    f"Inference successful. Output directory: {result_folder_dir}"
                )

                logger.info("Starting S3 upload")
                self.upload_folder_to_s3(
                    result_folder_dir, f"/song-requests/{song_data['request_id']}"
                )
                logger.info("S3 upload completed")

                # api 요청
                infer_complete_api_url = "https://asia-northeast3-homebrew-prod.cloudfunctions.net/processSongRequest"
                songRequestId = song_data["request_id"]
                infer_data_body = {
                    "songRequestId": songRequestId,
                    "audioPairList": song_uris,
                }
                logger.info(
                    f"api 전송을 위한 데이터 request id : {songRequestId}, urlList : {song_uris}"
                )
                response = requests.post(infer_complete_api_url, json=infer_data_body)
                logger.info(f"제조 완료 알림을 위한 api 전송 완료: {response.json()}")

                # 모든 작업이 성공적으로 완료된 후 SQS 메시지 삭제
                if not self.delete_sqs_message():
                    logger.error(
                        "Failed to delete SQS message after successful processing"
                    )
                    return False

            except Exception as e:
                logger.error(f"Error during inference or upload: {str(e)}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error in process_song_request: {str(e)}")
            return False

    def cleanup(self):
        """리소스 정리"""
        try:
            folders_to_clean = ["/app/guides", "/app/rvc_models", "/temp"]

            for folder in folders_to_clean:
                if os.path.exists(folder):
                    logger.info(f"Cleaning {folder}")
                    try:
                        for filename in os.listdir(folder):
                            file_path = os.path.join(folder, filename)
                            try:
                                if os.path.isfile(file_path) or os.path.islink(
                                    file_path
                                ):
                                    os.unlink(file_path)
                                elif os.path.isdir(file_path):
                                    shutil.rmtree(file_path)
                            except Exception as e:
                                logger.error(f"Failed to delete {file_path}: {e}")
                    except Exception as e:
                        logger.error(f"Error while cleaning {folder}: {e}")

            logger.info("Cleanup completed successfully")
            return True
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False


def main():
    """메인 실행 함수"""
    try:
        processor = SQSProcessor()

        if not processor.process_song_request():
            logger.error("Failed to process song request")
            sys.exit(1)

        if not processor.cleanup():
            logger.error("Failed to cleanup resources")
            sys.exit(1)

        logger.info("Process completed successfully")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Critical error in main: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
