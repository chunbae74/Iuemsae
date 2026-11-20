# 보안 설계

## 보호 대상 및 위협

| 보호 대상 | 위협 | 대응 |
| --- | --- | --- |
| 비밀번호, 로그인 세션 | 비밀번호 추측, DB 유출, 토큰 재사용 | 고비용 해시, 시도 횟수 제한, 토큰 회전 및 폐기 |
| 음성, 인식 문장 | 도청, 변조, 장기 보관 | 전송 구간 및 앱 계층 암호화, 메모리 처리 후 정리 |
| 기기, 요청 | 위조 기기 등록, 요청 변조 및 재전송 | 키 증명, 무결성 검증, 요청 서명, 시각·Nonce 검사 |
| 소통 정보 | DB 노출, 타 사용자 데이터로의 치환 | AES-GCM 암호화, 사용자 ID를 AAD로 결합 |
| 서버 개인키, DB 비밀번호 | 호스트 파일 복사, 불필요한 서비스의 접근 | DPAPI 보관, 서비스별 읽기 전용 메모리 전달 |
| 모델, 서버 자원 | 가중치 변조, 과도한 입력, 세션 고갈 | 해시 검증, 크기·시간·개수 제한 |

## 인증 및 세션

| 항목 | 구현 | 코드 |
| -- | --- | --- |
| 비밀번호 해시 | Argon2id (메모리 64MiB, 반복 3, 병렬도 2, 출력 32바이트), 해시마다 16바이트 무작위 Salt | [security.py](../server/auth/ieumsae_auth/security.py) |
| 로그인 실패 제한 | 5회 연속 실패 시 15분 잠금 | [lockout.py](../server/auth/ieumsae_auth/lockout.py) |
| 응답 시간 차이 완화 | 존재하지 않는 계정과 잠긴 계정에도 더미 Argon2id 검증 수행 | [auth.py](../server/auth/ieumsae_auth/routers/auth.py), [lockout.py](../server/auth/ieumsae_auth/lockout.py) |
| 토큰 관리 | 액세스 토큰 15분, 리프레시 토큰 30일. 리프레시 토큰은 HMAC-SHA256 값만 저장하며, 갱신 시마다 회전하고 재사용을 탐지 | [sessions.py](../server/auth/ieumsae_auth/sessions.py) |
| 현재 상태 확인 | 음성 요청마다 인증 서버에 세션·기기·동의 상태를 조회하며, 조회 실패 시 요청 거부 | [authorization.py](../server/stt/ieumsae_stt/authorization.py) |

Salt는 해시 문자열에 포함되어 `users.password_hash`에 함께 저장됩니다. DB 전체가 유출된 경우 로그인 잠금은 효과가 없으므로, Argon2id의 계산 비용과 비밀번호 강도가 중요합니다.

더미 해시는 프로세스 시작 시 한 번 생성하여 재사용합니다. 

리프레시 토큰은 갱신할 때마다 만료 시각이 새로 설정됩니다. 따라서 30일은 마지막 갱신 시점을 기준으로 합니다.

## 기기 및 요청 검증

Key Attestation과 Play Integrity는 기기 등록 시점에 검증하며, 이후 요청은 등록된 키의 서명과 인증 상태로 검증합니다. 

Play Integrity는 `PLAY_RECOGNIZED`와 `MEETS_DEVICE_INTEGRITY` 판정을 요구하므로, Google Play를 통해 배포된 앱에서만 기기 등록이 가능합니다.

## 통신 및 데이터 보호

| 항목 | 역할 | 코드 |
| --- | --- | --- |
| TLS 1.3 | 앱과 게이트웨이 간 구간 보호 | [nginx.conf](../server/gateway/nginx.conf), [Api.kt](../android/app/src/main/java/kr/ieumsae/app/data/Api.kt) |
| 공개키 고정 | 인증서 검증 후 SPKI SHA-256 값을 앱에 내장된 값과 비교 | [Api.kt](../android/app/src/main/java/kr/ieumsae/app/data/Api.kt) |
| HPKE | 앱이 생성한 AES 키를 서버 세션 공개키로 보호하여 전달 | [SttCrypto.kt](../android/app/src/main/java/kr/ieumsae/app/security/SttCrypto.kt), [crypto.py](../server/stt/ieumsae_stt/crypto.py) |
| AES-256-GCM | 음성 및 결과 암호화, IV와 AAD 사용 | [crypto.py](../server/stt/ieumsae_stt/crypto.py) |
| 사용자 ID AAD | 소통 정보 암호문을 다른 사용자 행으로 옮기면 복호화 실패 | [profile.py](../server/auth/ieumsae_auth/profile.py) |
| 저장 최소화 | 음성 및 인식 문장 미저장, 세션 종료 시 버퍼 정리 | [stt/sessions.py](../server/stt/ieumsae_stt/sessions.py), [SttSession.kt](../android/app/src/main/java/kr/ieumsae/app/stt/SttSession.kt) |

HPKE는 DHKEM(P-256, HKDF-SHA256), HKDF-SHA256, AES-256-GCM 조합을 사용합니다. 서버가 세션 공개키에 서명하고 앱이 이를 검증합니다. HPKE만으로는 사용자 인증과 재전송 방지가 보장되지 않으므로 요청 서명을 함께 적용하였습니다.

소통 정보는 서버 공통 32바이트 키로 암호화하며, 사용자 ID를 AAD로 사용하고 암호화마다 새로운 12바이트 IV를 생성합니다. 

공개키 고정은 앱이 위조 서버에 연결되는 것을 방지하고, 기기 서명은 서버가 위조 클라이언트를 차단하는 역할을 합니다. 공개키 검사는 TLS 핸드셰이크 직후, HTTP 요청 전에 수행하며 일치하지 않으면 요청을 전송하지 않습니다.