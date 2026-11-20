# API 명세서

본 서비스에서 제공하는 API의 요청 응답 및 인증 조건은 다음과 같습니다.

## 계정, 기기, 사용자

| 메서드 | 경로 | 인증 | 입력 → 응답 | 상태 |
| --- | --- | --- | --- | --- |
| GET | `/auth/health` | 공개 | 상태 | 200 |
| POST | `/auth/email/code` | 공개 | `email`, `purpose: signup` | 202 |
| POST | `/auth/email/verify` | 공개 | `email`, `purpose`, `code` → `emailToken`, `expiresIn` | 200 |
| POST | `/auth/signup` | 이메일 토큰 | `loginId`, `password`, `emailToken`, `consents`, `communication`(선택) | 201 |
| POST | `/auth/login` | 비밀번호 | `loginId`, `password`, `deviceId`(선택) → 사용자 정보, 토큰, 기기 등록 상태 | 200 |
| POST | `/auth/refresh` | 리프레시 토큰 | `refreshToken` → 새 토큰 | 200 |
| POST | `/auth/logout` | 리프레시 토큰 | `refreshToken` | 204 |
| PUT | `/auth/password` | Bearer | `currentPassword`, `newPassword` | 204 |
| POST | `/auth/find-id` | 공개 | `email` | 202 |
| POST | `/auth/password-reset/request` | 공개 | `loginId`, `email` | 202 |
| POST | `/auth/password-reset/confirm` | 재설정 코드 | `loginId`, `code`, `newPassword` | 204 |
| GET | `/auth/session/status` | Bearer (기기 결합) | → `active`, `userId`, `deviceId`, `ttsConsent` | 200 |
| POST | `/device/challenge` | Bearer | → `challenge`, `expiresIn` | 200 |
| POST | `/device/register` | Bearer | `challenge`, `publicKey`, `keyAttestationChain`, `integrityToken`, `sdkInt` | 201 |
| DELETE | `/device/{device_id}` | Bearer | 기기 및 연결된 세션 해제 | 204 |
| GET | `/user/profile` | Bearer | → 마스킹된 이메일, 소통 정보, 동의 상태 | 200 |
| PUT | `/user/communication` | Bearer | `consent`, `speechLevel`, `comprehensionLevel`, `showToListener` | 204 |
| DELETE | `/user/communication` | Bearer | 소통 정보 삭제 | 204 |
| PUT | `/user/consents/tts` | Bearer | `agree` | 204 |
| DELETE | `/user` | Bearer | `password` | 204 |

로그인 시 `deviceId`를 전달한 경우, 해당 기기 키로 요청을 서명해야 기기와 결합된 세션으로 인정됩니다. 기기를 등록하지 않은 사용자는 로그인 → challenge 발급 → 기기 등록 → 토큰 갱신 순서로 진행합니다.

## STT, TTS

| 메서드 | 경로 | 인증 | 입력 → 응답 | 상태 |
| --- | --- | --- | --- | --- |
| GET | `/system/health` | 공개 | STT·TTS 사용 가능 여부 | 200 |
| GET | `/system/keys` | 공개 | 서버 서명 공개키 및 서명 | 200 |
| POST | `/stt/session` | 기기 서명 | `mode: translate` → 세션 ID, HPKE 공개키, 서명, 만료 시각, 제한값 | 200 |
| POST | `/stt/session/{session_id}/key` | 기기 서명 | `enc`, `ciphertext` | 204 |
| POST | `/stt/session/{session_id}/chunk` | 기기 서명 | `seq`, `timestamp`, `iv`, `ciphertext` | 200 |
| POST | `/stt/session/{session_id}/finalize` | 기기 서명 | `lastSeq` → 암호화된 결과 | 200 |
| DELETE | `/stt/session/{session_id}` | 기기 서명 | 세션 취소 | 204 |
| POST | `/tts/session` | 기기 서명 + TTS 동의 | → 세션 ID, HPKE 공개키, 서명 | 200 |
| POST | `/tts/session/{session_id}/speak` | 기기 서명 + TTS 동의 | `enc`, `ciphertext` → 암호화된 음성 | 200 |

## 요청 서명

| 헤더 | 값 |
| --- | --- |
| `X-Device-Id` | 등록된 기기 ID |
| `X-Timestamp` | 요청 시각 (Unix epoch, 밀리초) |
| `X-Nonce` | 요청마다 새로 생성한 URL-safe 문자열 |
| `X-Signature` | 기기 P-256 개인키로 생성한 ECDSA-SHA256 서명 (Base64) |

서명 대상은 다음 6개 항목을 줄바꿈으로 연결한 UTF-8 문자열입니다. 마지막 항목은 실제 전송하는 본문 바이트의 SHA-256 값을 Base64로 인코딩한 것입니다.

```text
IEUMSAE-SIG-V1
HTTP_METHOD
/request/path
TIMESTAMP
NONCE
BASE64_SHA256_OF_BODY
```

서버 시각과의 차이가 1분 이상 발생할 시, 해당 요청을 거부합니다. 

## STT 요청 예시

세션 생성

```json
{"mode":"translate"}
```

세션 키 전달 (`enc`는 HPKE 캡슐화 값)

```json
{"enc":"<Base64>","ciphertext":"<Base64>"}
```

음성 조각 전송. `seq`는 0부터 시작합니다. PCM 형식은 16kHz, 모노, 16비트 little-endian이며 1초당 32,000바이트입니다.

```json
{"seq":0,"timestamp":1795100000000,"iv":"<12바이트 IV, Base64>","ciphertext":"<암호문+GCM 태그, Base64>"}
```

종료 요청 (마지막 조각이 0번인 경우)

```json
{"lastSeq":0}
```

서버는 0번부터 `lastSeq`까지 모든 조각이 수신되었는지 확인합니다. 응답은 `iv`, `ciphertext`로 구성되며, 복호화하면 `{"text":"인식 문장"}` 형태입니다. 음성 조각의 AAD에는 세션 ID, 순번, 시각이 포함되고 결과의 AAD에는 세션 ID가 포함됩니다. 정확한 형식은 [crypto.py](../server/stt/ieumsae_stt/crypto.py)를 참고합니다.

## 오류 응답

인증 서버

```json
{"error":{"code":"invalid_credentials"}}
```

음성 서버

```json
{"error":"missing_chunks"}
```

미들웨어 단계의 오류나 예상하지 못한 오류는 인증 서버에서도 `{"error":"internal_error"}` 형식으로 반환될 수 있습니다. Nginx에서 직접 거부한 요청은 JSON 형식이 아닐 수 있습니다.

| 상태 | 코드 | 앱 처리 |
| --- | --- | --- |
| 400 | 잘못된 코드, 암호문, 증명 | 입력값 확인. 복호화 실패 시 요청 중단 |
| 401 | `invalid_credentials`, `invalid_token`, `invalid_signature` | 인증 상태 확인. 재시도 시 새 Nonce 사용 |
| 403 | `device_not_registered`, TTS 미동의 | 기기 등록 또는 동의 화면으로 안내 |
| 404 | `session_not_found` | 새 세션 시작 |
| 408 | `request_timeout` | 네트워크 상태 확인 |
| 409 | `missing_chunks`, `duplicate_chunk`, `session_finalizing` | 업로드 순서 확인 |
| 413 | 요청 크기 초과 | 입력 크기 축소 |
| 422 | `invalid_request` | 형식, 길이, 범위 확인 |
| 423 | `account_locked` | 15분 잠금 안내 |
| 429 | 요청 빈도 또는 세션 수 초과 | 일정 시간 후 재시도 |
| 500 | `internal_error` | 일반 오류 메시지 표시 |
| 503 | `stt_busy`, `stt_unavailable`, `authorization_unavailable` | 일정 시간 후 재시도 안내 |

요청 본문은 최대 64KiB입니다.