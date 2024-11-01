import os
import sys
import re
import json
import sox
import shutil

from main import voice_change, find_full_path


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
                print(f"{filename}의 피치가 {semitones} 반음만큼 변경되었습니다.")
            elif semitones == 0:
                shutil.copy(input_filepath, output_filepath)


if __name__ == "__main__":
    song_datas_str = sys.argv[1]
    request_date_str = sys.argv[2]
    song_datas = json.loads(song_datas_str)
    request_date = int(request_date_str)
    print(song_datas)

for song_data in song_datas:
    request_id = song_data["request_id"]
    request_user_id = song_data["request_user_id"]
    song_title = song_data["song_title"]
    voice_model = song_data["voice_model"]
    pitch_value = song_data["pitch_value"]
    isMan = song_data["isMan"]

    input_paths = find_full_path(song_title, isMan)
    # 파일 경로를 숫자에 따라 정렬
    sorted_input_paths = sorted(input_paths, key=extract_number)
    # 결과물 생성 폴더
    if not os.path.exists(
        f"/content/drive/MyDrive/songRequest/results/{request_date}/{request_user_id}/{request_id}/[{pitch_value}][{voice_model}]{song_title}"
    ):
        os.makedirs(
            f"/content/drive/MyDrive/songRequest/results/{request_date}/{request_user_id}/{request_id}/[{pitch_value}][{voice_model}]{song_title}"
        )

    for input_path in sorted_input_paths:
        file_name = os.path.basename(input_path)
        output_path = f"/content/drive/MyDrive/songRequest/results/{request_date}/{request_user_id}/{request_id}/[{pitch_value}][{voice_model}]{song_title}/{file_name}"
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
        # mr 처리
        mr_input_path = os.path.dirname(input_path)
        mr_output_path = f"/content/drive/MyDrive/songRequest/results/{request_date}/{request_user_id}/{request_id}/[{pitch_value}][{voice_model}]{song_title}"
        process_mr_files(mr_input_path, mr_output_path, pitch_value)
