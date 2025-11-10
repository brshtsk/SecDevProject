import os
import sys


def get_required_secrets():
    raw = os.getenv("REQUIRED_SECRETS", "SECRET_KEY,DATABASE_URL")
    return [s.strip() for s in raw.split(",") if s.strip()]


def fail(msg: str, code: int = 1):
    sys.stderr.write(msg.strip() + "\n")
    sys.exit(code)


def main(argv):
    missing = [s for s in get_required_secrets() if not os.getenv(s)]
    if missing:
        fail(
            f"Startup check failed: missing required secrets: {', '.join(missing)}",
            code=2,
        )
    # Успешный путь — тишина, чтобы не загрязнять логи
    if argv:
        os.execvp(argv[0], argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
