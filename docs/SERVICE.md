# 서비스 및 요구사항

## 문제 정의

구음장애인은 발음이 불명확하여 처음 만나는 상대와의 대면 의사소통에 어려움을 겪습니다. 이음새는 사용자가 자신의 목소리로 말하면 인식된 문장을 큰 글씨로 표시하고, 필요한 경우 음성으로 출력합니다.

주요 활용 상황은 병원에서의 증상 설명, 복지시설에서의 도움 요청, 공공기관에서의 민원 전달입니다.

## 기능 요구사항

| 번호 | 요구사항 | 동작 | 구현 |
| --- | --- | --- | --- |
| F-01 | 이메일 인증 가입 | 인증 코드 확인 후 발급된 토큰으로 계정 생성 | [auth.py](../server/auth/ieumsae_auth/routers/auth.py) |
| F-02 | 대면 음성인식 | 녹음 → 암호화 조각 업로드 → 종료 → 결과 표시 | [SttSession.kt](../android/app/src/main/java/kr/ieumsae/app/stt/SttSession.kt) |
| F-03 | 상대방 표시 | 큰 글씨, 상대방 방향 180도 화면 전환 | [ConversationScreen.kt](../android/app/src/main/java/kr/ieumsae/app/ui/screens/ConversationScreen.kt) |
| F-04 | 이어 말하기 | 이전 인식 완료 후 새 세션으로 녹음 시작 | [ConversationScreen.kt](../android/app/src/main/java/kr/ieumsae/app/ui/screens/ConversationScreen.kt) |
| F-05 | 감정 음성 출력 | 동의 시 외부 감정 합성, 미동의 시 기기 TTS | [EmotionSpeaker.kt](../android/app/src/main/java/kr/ieumsae/app/tts/EmotionSpeaker.kt) |
| F-06 | 대화 배려 안내 | 사용자가 선택한 이해 수준 및 표시 설정 반영 | [CommunicationText.kt](../android/app/src/main/java/kr/ieumsae/app/data/CommunicationText.kt) |
| F-07 | 동의 철회 및 정보 삭제 | 소통 정보 삭제, TTS 동의 변경, 회원 탈퇴 | [user.py](../server/auth/ieumsae_auth/routers/user.py) |

## 대화 흐름

1. 사용자가 말하기 버튼을 누릅니다. 최초 실행 시 마이크 권한을 요청합니다.
2. 녹음 중 약 1초 분량씩 음성을 암호화하여 서버로 전송합니다.
3. "다 말했어요" 버튼을 누르면 남은 음성과 종료 요청을 전송합니다.
4. 서버가 전체 음성을 인식하면 결과 문장을 큰 글씨로 표시합니다.
5. 화면을 상대방 방향으로 전환하거나 음성 출력 기능을 사용합니다.
6. 이어 말하기를 선택하면 새 세션과 새 키로 다음 녹음을 시작합니다.

1회 녹음은 최대 30초입니다. 1초는 업로드 단위이며, 인식 결과는 녹음 종료 후 한 번에 반환됩니다.

## 전문가 인터뷰 반영

강원특별자치도장애인종합복지관의 작업치료사, 물리치료사, 언어치료사를 대상으로 인터뷰를 진행하였습니다. 

| 의견                                          | 반영 기능             |
|---------------------------------------------|-------------------|
| 구음장애인이 자신의 목소리로 소통할 수 있다는 점이 긍정적임           | -                 |
| 병원, 복지시설, 공공기관에서 활용 가능성이 있음                 | -                 |
| 발화자의 이해 수준을 상대방에게 알려야 상대방이 의사소통 시 배려해줄 수 있음 | 발화자의 지적 수준 화면에 표기 |
| 감정과 뉘앙스 전달이 필요함                             | 감정 TTS            |