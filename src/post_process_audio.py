from pedalboard import load_plugin
from pedalboard.io import AudioFile
from pydub import AudioSegment
import numpy as np


def apply_reverb(result_folder,index,vocal_file_name):
    # 리버브 플러그인 로드
    reverb = load_plugin("/app/audio_plugins/TAL-Reverb-4.vst3")

    # 기본 리버브 세팅
    reverb.on_off = 1.0  # On
    reverb.bypass = False  # Off
    reverb.size = 55.0  # Size 55
    reverb.damp = 20.0  # Damp 20
    reverb.delay = "0.1000 s"  # Delay 0.1
    reverb.diffuse = 100.0  # Diffuse 100
    reverb.stereo = 100.0  # Stereo 100
    reverb.dry = 100.0  # Dry 100
    reverb.wet = 35.0  # Wet 35

    file_name = vocal_file_name.replace("_vocal.mp3", "")
    
    # 오디오 처리 및 저장
    with AudioFile(f"{result_folder}/{file_name}_vocal.mp3") as f:
        audio = f.read(f.frames)
        samplerate = f.samplerate

        # 현재 오디오 shape 확인
        print("Original audio shape:", audio.shape)

        # 차원 변환 - 모노를 스테레오로
        if len(audio.shape) == 1:  # 단일 차원 (모노)
            audio = np.array([audio, audio])
        elif len(audio.shape) == 2 and audio.shape[0] == 1:  # (1, samples) 형태
            audio = np.array([audio[0], audio[0]])
        elif len(audio.shape) == 2 and audio.shape[1] == 1:  # (samples, 1) 형태
            audio = np.array([audio.T[0], audio.T[0]])

        # 변환된 shape 확인
        print("Converted audio shape:", audio.shape)

        # 리버브 적용
        effected = reverb(audio, samplerate)

        # 결과 저장
        with AudioFile(
            f"{result_folder}/{file_name}_reverb.mp3",
            "w",
            samplerate,
            num_channels=2,
        ) as out_f:
            out_f.write(effected)

    return f"{result_folder}/{file_name}_reverb.mp3"


def mix_audio(vocal_path, mr_path, output_path):
    # 오디오 파일 로드
    vocal = AudioSegment.from_file(vocal_path)
    mr = AudioSegment.from_file(mr_path)

    # 두 오디오 파일 병합 (overlay)
    combined = vocal.overlay(mr)

    # MP3로 export
    combined.export(output_path, format="mp3")
