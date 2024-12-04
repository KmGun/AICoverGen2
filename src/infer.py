import io
import os
import sys
import re
import json
import sox
import shutil
import logging
import boto3


from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from botocore.exceptions import NoCredentialsError
from main import voice_change
from post_process_audio import apply_reverb, mix_audio
from dotenv import load_dotenv


load_dotenv()


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id="YOUR_ACCESS_KEY",
    aws_secret_access_key="YOUR_SECRET_KEY",
    region_name="ap-northeast-2",
)


def process_guide_folders(guide_folders, root_folder):
    # 숫자 prefix로 정렬
    sorted_folders = sorted(guide_folders, key=lambda x: int(x.split("_")[0]))

    # 각 폴더에 대해 full path 생성
    result_paths = [
        f"{root_folder}/{folder}/{folder}_vocal.mp3" for folder in sorted_folders
    ]

    return result_paths


# 파일 경로에서 1_,2_ 를 추출하는 함수
def extract_number(file_path):
    # 파일명 추출
    file_name = os.path.basename(file_path)
    # 파일명에서 숫자 추출
    match = re.match(r"(\d+)_", file_name)
    return int(match.group(1)) if match else float("inf")


def change_pitch_sox(input_filepath, output_filepath, semitones):
    tfm = sox.Transformer()
    tfm.pitch(semitones)
    tfm.build(input_filepath, output_filepath)


def process_mr_files(input_directory, output_directory, semitones):
    for filename in os.listdir(input_directory):
        if filename.endswith("_mr.mp3"):
            input_filepath = os.path.join(input_directory, filename)
            output_filepath = os.path.join(output_directory, filename)
            if semitones != 0:
                change_pitch_sox(input_filepath, output_filepath, semitones)
                # print(f"{filename}의 피치가 {semitones} 반음만큼 변경되었습니다.")
            elif semitones == 0:
                shutil.copy(input_filepath, output_filepath)

            return output_filepath


def connect_to_google_drive():
    # 인증 정보 JSON 파일 경로
    credentials_path = "/app/homebrew-prod-1aeee50b74d5.json"
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    return service


# def download_file(service, file_id, destination):
#     request = service.files().get_media(fileId=file_id)
#     with open(destination, "wb") as f:
#         downloader = MediaIoBaseDownload(f, request)
#         done = False
#         while not done:
#             status, done = downloader.next_chunk()
#             print("Download progress: %d%%" % int(status.progress() * 100))


def download_folder_by_folder_id(service, folder_id, destination_folder):
    # 폴더의 모든 파일 목록을 가져옵니다.
    query = f"'{folder_id}' in parents"
    results = service.files().list(q=query).execute()
    items = results.get("files", [])

    if not items:
        print("No files found in the folder.")
    else:
        # print(f"Found {len(items)} files in the folder:")
        for item in items:
            # print(f" - {item['name']} ({item['id']})")
            file_destination = os.path.join(destination_folder, item["name"])
            download_file(service, item["id"], file_destination)


def download_google_drive_folder(service, folder_id, local_path, folder_name=None):
    """
    Google Drive의 특정 폴더를 로컬에 다운로드합니다.

    Args:
        service: Google Drive API 서비스 객체
        folder_id (str): Google Drive 폴더 ID
        local_path (str): 다운로드할 로컬 경로
        folder_name (str, optional): 다운로드할 특정 하위 폴더 이름. 지정 시 해당 폴더를 찾아 폴더 구조대로 다운로드
    """

    def download_file(file_metadata, path):
        """개별 파일을 다운로드합니다."""
        file_id = file_metadata["id"]
        file_name = file_metadata["name"]
        file_path = os.path.join(path, file_name)

        if "google-apps" in file_metadata["mimeType"]:
            return

        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        try:
            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)
            with open(file_path, "wb") as f:
                f.write(fh.read())

        except Exception as e:
            print(f"Error downloading {file_name}: {str(e)}")

    def find_specific_folder(parent_folder_id, target_folder_name):
        """특정 이름의 하위 폴더를 찾습니다."""
        query = f"'{parent_folder_id}' in parents and name = '{target_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = (
            service.files()
            .list(q=query, fields="files(id, name)", pageSize=1)
            .execute()
        )

        items = results.get("files", [])
        return items[0] if items else None

    def process_folder(folder_id, current_path):
        """폴더 내의 모든 파일과 하위 폴더를 재귀적으로 처리합니다."""
        # print(f"\nProcessing folder: {folder_id}")
        # print(f"Local path: {current_path}")

        if not os.path.exists(current_path):
            os.makedirs(current_path)
            # print(f"Created directory: {current_path}")

        try:
            # trashed = false 조건 추가하고 파일 정렬
            query = f"'{folder_id}' in parents and trashed = false"
            # print(f"Executing query: {query}")

            results = (
                service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=1000,
                    orderBy="folder,name",
                )
                .execute()
            )

            items = results.get("files", [])
            # print(f"Found {len(items)} items in folder")

            if not items:
                # print("No files found in this folder.")
                return

            for item in items:
                # print(f"\nProcessing item: {item['name']} ({item['mimeType']})")

                if item["mimeType"] == "application/vnd.google-apps.folder":
                    new_folder_path = os.path.join(current_path, item["name"])
                    # print(f"Found subfolder: {item['name']}")
                    process_folder(item["id"], new_folder_path)
                else:
                    download_file(item, current_path)

        except Exception as e:
            print(f"Error processing folder {folder_id}: {str(e)}")

    # print(f"Starting download process")

    if folder_name:
        # print(f"Searching for specific folder: {folder_name}")
        folder_info = find_specific_folder(folder_id, folder_name)

        if folder_info:
            # print(f"Found folder '{folder_name}'. Starting download...")
            # 상위 폴더 생성하고 그 안에 target 폴더 생성
            target_path = os.path.join(local_path, folder_name)
            process_folder(folder_info["id"], target_path)
        else:
            print(
                f"Error: Folder '{folder_name}' not found in the specified parent folder"
            )
            return
    else:
        # print(f"Downloading entire folder {folder_id} to {local_path}")
        process_folder(folder_id, local_path)

    # print("Download process completed")


def infer_ai_cover(
    request_id, request_user_id, song_title, guide_id, voice_model, isMan
):
    logger.info(
        f"Starting inference with parameters: request_id={request_id}, guide_id={guide_id}, voice_model={voice_model}"
    )

    song_urls = []

    try:
        # 1. 가이드 폴더 다운
        logger.info("가이드 폴더 다운 시작")
        drive_service = connect_to_google_drive()

        # 특정 폴더의 ID와 다운로드할 경로를 설정합니다.
        folder_id = guide_id  # 폴더 ID로 변경
        destination_folder = f"/app/guides/{guide_id}"  # 다운로드할 경로로 변경

        # 다운로드할 폴더를 생성합니다.
        os.makedirs(destination_folder, exist_ok=True)

        # 폴더 내 모든 파일을 다운로드합니다.
        download_google_drive_folder(drive_service, folder_id, destination_folder)
        logger.info("가이드 폴더 다운 완료")
        # 2. 파일 경로를 숫자에 따라 정렬

        # 다운로드된 가이드 폴더 찾기 (서브디렉토리)
        guide_folders = os.listdir(destination_folder)
        # scan_directory("/app/guides")

        sorted_input_paths = process_guide_folders(guide_folders, destination_folder)

        # 모델에 맞는 pitch 값을 가져옵니다.
        pitch_values_by_model = {
            "ljb": [-1, 0, 1],
            "ssk": [-2, -1],
            "ssh": [0, 1],
        }

        if voice_model in pitch_values_by_model:
            model_pitch_values = pitch_values_by_model[voice_model]
        else:
            model_pitch_values = [0]

        # 보이스 모델 다운로드
        logger.info("보이스 모델 다운로드")
        download_google_drive_folder(
            drive_service,
            "1nlUfim_6GH3OsQrokITpLGISDoiMpT8X",
            "/app/rvc_models",
            voice_model,
        )

        # 추론 시작
        for pitch_value in model_pitch_values:
            # 결과물 생성 폴더
            result_folder = (
                f"./temp/{request_id}/[{pitch_value}][{voice_model}]{song_title}"
            )
            os.makedirs(result_folder)
            logger.info(
                f"추론 + mr처리 + 믹싱 시작 : pitch={pitch_value}, model={voice_model}, title={song_title}"
            )
            for index, input_path in enumerate(sorted_input_paths):
                file_name = os.path.basename(input_path)
                output_path = f"{result_folder}/{file_name}"
                try:
                    voice_change(
                        voice_model,
                        input_path,
                        output_path,
                        pitch_value,
                        f0_method="rmvpe",
                        index_rate=0.66,
                        filter_radius=3,
                        rms_mix_rate=0.25,
                        protect=0.33,
                        crepe_hop_length=128,
                        is_webui=0,
                    )

                except Exception as e:
                    print(f"추론 중 에러 발생: {str(e)}")
                    raise

                # mr 처리
                try:
                    mr_input_path = os.path.dirname(input_path)
                    mr_output_path = result_folder
                    mr_file_path = process_mr_files(
                        mr_input_path, mr_output_path, pitch_value
                    )
                except Exception as e:
                    print(f"MR 처리중 오류: {str(e)}")
                    raise

                # 믹싱
                ai_vocal_path = apply_reverb(result_folder,index,file_name)
                real_file_name = file_name.replace("_vocal.mp3", "")
                # mix_audio(
                #     ai_vocal_path,
                #     mr_file_path,
                #     f"{result_folder}/[{pitch_value}][{voice_model}]{index}_{song_title}_result.mp3",
                # )
                audioPair = {
                    "mrUrl" : f"https://song-request-bucket-1.s3.ap-northeast-2.amazonaws.com//song-requests/{request_id}/[{pitch_value}][{voice_model}]{song_title}/{real_file_name}_mr.mp3",
                    "vocalUrl" : f"https://song-request-bucket-1.s3.ap-northeast-2.amazonaws.com//song-requests/{request_id}/[{pitch_value}][{voice_model}]{song_title}/{real_file_name}_reverb.mp3",
                }
                song_urls.append(audioPair)

        result_path = f"./temp/{request_id}"
        logger.info(
            "추론 + mr처리 + 믹싱 완료 : ",
            voice_model,
            song_title,
        )
        return result_path, song_urls

    except Exception as e:
        print(f"Error in infer_ai_cover: {str(e)}")
        if hasattr(e, "stderr"):
            print(f"Stderr output: {e.stderr}")
        raise
