import argparse
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_secrets import SecretStore


ROOT = Path(__file__).resolve().parent


def prepare(docker, gpu=False):
    command = [docker, 'compose', '--project-directory', str(ROOT), '-f', str(ROOT / 'docker-compose.yml')]
    if gpu:
        command += ['-f', str(ROOT / 'docker-compose.gpu.yml')]
    result = subprocess.run(command + ['config', '--format', 'json'], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('COMPOSE_CONFIGURATION_REQUIRED')
    configuration = json.loads(result.stdout)
    SecretStore(ROOT / 'secrets').runtime_payload()
    for name in ('server.pem',):
        path = ROOT / 'secrets' / 'tls' / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('TLS_FILES_REQUIRED')
    model = ROOT / 'stt' / 'models' / 'ieumsae_stt.pt'
    if not model.is_file():
        raise ValueError('MODEL_FILE_REQUIRED')
    with model.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    expected = configuration['services']['stt']['environment']['STT_MODEL_SHA256']
    if not hmac.compare_digest(digest, str(expected).lower()):
        raise ValueError('MODEL_INTEGRITY_FAILED')
    result = subprocess.run([docker, 'info', '--format', '{{.ServerVersion}}'], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('CONTAINER_ENGINE_UNAVAILABLE')
    return command


def main():
    parser = argparse.ArgumentParser(description='운영 환경 설정을 확인하고 이음새 API 서버를 실행합니다.')
    parser.add_argument('--check', action='store_true', help='설정과 파일을 확인하고 서버를 시작하지 않습니다.')
    parser.add_argument('--gpu', action='store_true', help='NVIDIA GPU 사용 구성을 적용합니다.')
    args = parser.parse_args()
    docker = shutil.which('docker')
    if not docker:
        print('DOCKER_REQUIRED')
        return 1
    try:
        command = prepare(docker, args.gpu)
        if args.check:
            print('CONFIGURATION_OK')
            return 0
        result = subprocess.run(command + ['build', 'auth', 'stt', 'secret-loader', 'secret-memory'], capture_output=True)
        if result.returncode:
            print('SERVER_START_FAILED')
            return 1
        # Keep tmpfs volumes mounted while the one-shot loader exits and apps start.
        result = subprocess.run(command + ['up', '--detach', '--no-deps', 'secret-memory'], capture_output=True)
        if result.returncode:
            print('SECRET_PROJECTION_FAILED')
            return 1
        # Pipe secrets in memory; no command-line/env or persistent plaintext staging.
        result = subprocess.run(
            command + ['run', '--rm', '--no-deps', '-T', 'secret-loader'],
            input=SecretStore(ROOT / 'secrets').runtime_payload(), capture_output=True,
        )
        if result.returncode:
            print('SECRET_PROJECTION_FAILED')
            return 1
        result = subprocess.run(command + ['up', '--detach', '--build'], capture_output=True)
        if result.returncode:
            print('SERVER_START_FAILED')
            return 1
        print('SERVER_START_REQUESTED')
        return 0
    except ValueError as error:
        allowed = {'COMPOSE_CONFIGURATION_REQUIRED', 'SECRET_FILES_REQUIRED', 'TLS_FILES_REQUIRED',
                   'MODEL_FILE_REQUIRED', 'MODEL_INTEGRITY_FAILED', 'CONTAINER_ENGINE_UNAVAILABLE'}
        print(str(error) if str(error) in allowed else 'CONFIGURATION_INVALID')
        return 1
    except (OSError, subprocess.TimeoutExpired, KeyError, TypeError):
        print('CONFIGURATION_CHECK_FAILED')
        return 1


if __name__ == '__main__':
    sys.exit(main())
