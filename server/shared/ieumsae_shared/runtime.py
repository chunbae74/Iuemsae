import ipaddress
import os
import logging
import sys


EVENTS = frozenset({
    'REQUEST_FAILED', 'STARTUP_FAILED', 'MAIL_FAILED', 'ATTESTATION_REJECTED',
    'INTEGRITY_REJECTED', 'TTS_FAILED', 'MODEL_UNAVAILABLE', 'MODEL_INTEGRITY_FAILED',
})


class SafeFormatter(logging.Formatter):
    def format(self, record):
        event = record.msg if isinstance(record.msg, str) and record.msg in EVENTS else 'SERVICE_EVENT'
        return f'{record.levelname} {event}'


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter())
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'httpx', 'httpcore', 'sqlalchemy'):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.WARNING)
    logging.captureWarnings(True)


def main():
    configure_logging()
    targets = {'auth': 'ieumsae_auth.main:app', 'stt': 'ieumsae_stt.main:app'}
    if len(sys.argv) != 2 or sys.argv[1] not in targets:
        logging.error('STARTUP_FAILED')
        return 1
    try:
        trusted = os.environ.get("TRUSTED_PROXY_IPS", "127.0.0.1")
        for network in trusted.split(","):
            ipaddress.ip_network(network.strip(), strict=False)
        import uvicorn
        uvicorn.run(targets[sys.argv[1]], host='0.0.0.0', port=8000,
                    log_config=None, access_log=False, server_header=False,
                    proxy_headers=True, forwarded_allow_ips=trusted,
                    limit_concurrency=64, timeout_keep_alive=5)
    except (ValueError, TypeError):
        logging.error('STARTUP_FAILED', extra={'failure_kind': 'configuration'})
        return 1
    except OSError:
        logging.error('STARTUP_FAILED', extra={'failure_kind': 'io'})
        return 1
    except (ImportError, RuntimeError):
        logging.error('STARTUP_FAILED', extra={'failure_kind': 'dependency'})
        return 1
    except Exception:
        # Last-resort boundary: never expose configuration in a traceback.
        logging.error('STARTUP_FAILED', extra={'failure_kind': 'unexpected'})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
