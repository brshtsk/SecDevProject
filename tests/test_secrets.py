import os
import subprocess
import sys


def run_prestart(env, args):
    cmd = [sys.executable, "-m", "scripts.prestart"] + args
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_fail_fast_missing_required_secret():
    env = {
        k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DATABASE_URL")
    }
    env.pop("SECRET_KEY", None)
    env.pop("DATABASE_URL", None)
    r = run_prestart(env, [sys.executable, "-c", "print('OK')"])
    assert r.returncode != 0
    assert "missing required secrets" in (r.stderr or "").lower()
    assert ("SECRET_KEY" in r.stderr) or ("DATABASE_URL" in r.stderr)


def test_pass_when_secrets_present():
    env = os.environ.copy()
    env["SECRET_KEY"] = "dummy"
    env["DATABASE_URL"] = "sqlite:///./data/app.db"
    r = run_prestart(env, [sys.executable, "-c", "print('OK')"])
    assert r.returncode == 0
    assert "OK" in (r.stdout or "")


def test_secret_not_present_in_logs():
    secret = "supersecretvalue123"
    env = os.environ.copy()
    env["SECRET_KEY"] = secret
    env["DATABASE_URL"] = "sqlite:///./data/app.db"
    r = run_prestart(env, [sys.executable, "-c", "print('OK')"])
    blob = (r.stdout or "") + (r.stderr or "")
    assert secret not in blob
