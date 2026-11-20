# 모델 카드

## 개요

한국어 구음장애 발화를 텍스트로 변환하는 STT 모델입니다,

## 모델 사양

| 항목 | 값 |
| --- | --- |
| 구조 | VGG 계열 CNN 특징 추출기 + Transformer encoder/decoder |
| 입력 | 16kHz, 모노, PCM16 little-endian, 최대 30초 |
| 음향 특징 | 80차원 log-mel filterbank, window 25ms, hop 10ms |
| CNN | 3×3 합성곱 4개, max pooling 2개, 512차원 선형 투영 |
| 층 수 | encoder 12층, decoder 6층 |
| 차원 | hidden 512, FFN 2048 |
| 실행 장치 | `auto`: CUDA 사용 가능 시 GPU, 그 외 CPU |


"VGG 계열"은 VGG16/19 등의 이미지 분류 모델을 그대로 사용한다는 의미가 아니라, 작은 합성곱 층을 쌓고 pooling하는 VGG 방식의 음성 특징 추출기를 의미합니다. 

## 입출력

녹음이 종료되면 서버가 PCM 조각을 결합하여 한 번에 인식합니다. 처리 순서는 특징 추출 → CNN → Transformer → 토큰의 문자열 변환이며, 결과는 암호화하여 앱에 전송합니다.