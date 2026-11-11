"""Which S3 server can replace the deleted ``minio/minio`` image in our container tests?

$0, local Docker only. MinIO stopped publishing community images in Oct 2025 and removed
them from Docker Hub in Sep 2026, so ``tests/integration/constants.py::MINIO_IMAGE`` no
longer resolves and ``minio_storage_uri`` cannot start. For each candidate this script
starts the container, measures time-to-healthy, does the minimum bootstrap the server
needs, then runs the REAL ``tests/integration/test_storage_s3.py`` against it — with the
conftest fixture swapped for one that yields the already-running endpoint.

Candidates: Chainguard's free MinIO build, RustFS, Garage.

Pre-registered readings (written before the first run):

| Outcome per candidate | Reading |
|---|---|
| image does not resolve | eliminated |
| N/N pass, no bootstrap beyond env + bucket mkdir | drop-in; smallest diff wins |
| N/N pass, needs config file / CLI bootstrap | works, but loses to a drop-in (heavy rewrite) |
| some fail | incompatible with our s3fs usage on that axis; record which test |
| 0/N or never healthy | unmeasured for that candidate, not "broken" — record the last log lines |

    uv run --group containers python scripts/dev/spike_s3_test_backend.py [candidate ...]
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEY, SECRET, BUCKET = "minioadmin", "minioadmin", "gflow-test"
# Garage only accepts its own key-id shape: "GK" + 24 hex, secret 64 hex.
GARAGE_KEY, GARAGE_SECRET = "GK" + "0" * 24, "0" * 64

GARAGE_TOML = """\
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "sqlite"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "{rpc}"
[s3_api]
s3_region = "us-east-1"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"
[admin]
api_bind_addr = "[::]:3903"
"""

CANDIDATES: dict[str, dict[str, object]] = {
    "chainguard-minio": {
        "image": "cgr.dev/chainguard/minio:latest",
        "args": ["server", "/data"],
        "env": {"MINIO_ROOT_USER": KEY, "MINIO_ROOT_PASSWORD": SECRET},
        "port": 9000,
        "health": "/minio/health/live",
    },
    "rustfs": {
        "image": "rustfs/rustfs:1.0.3",
        "args": [],
        "env": {"RUSTFS_ACCESS_KEY": KEY, "RUSTFS_SECRET_KEY": SECRET},
        "port": 9000,
        "health": "/health",
    },
    "garage": {
        "image": "dxflrs/garage:v2.4.1",
        "args": [],
        "env": {},
        "port": 3900,
        "health_port": 3903,
        "health": "/health",
    },
}


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 — localhost only
            return resp.status == 200
    except Exception:
        return False


def _garage_bootstrap(name: str) -> None:
    def garage(*a: str) -> str:
        return _run("docker", "exec", name, "/garage", *a)

    for _ in range(60):
        try:
            node = garage("node", "id", "-q").split("@")[0]
            break
        except subprocess.CalledProcessError:
            time.sleep(0.5)
    garage("layout", "assign", "-z", "dc1", "-c", "1G", node)
    garage("layout", "apply", "--version", "1")
    garage("key", "import", "--yes", "-n", "gflow", GARAGE_KEY, GARAGE_SECRET)
    garage("key", "allow", "--create-bucket", "gflow")


def measure(cand: str) -> str:
    c = CANDIDATES[cand]
    name = f"spike-s3-{cand}-{secrets.token_hex(3)}"
    key, secret = (GARAGE_KEY, GARAGE_SECRET) if cand == "garage" else (KEY, SECRET)
    cmd = ["docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1::{c['port']}"]
    tmp = ROOT / "tmp" / name
    if cand == "garage":
        tmp.mkdir(parents=True)
        (tmp / "garage.toml").write_text(GARAGE_TOML.format(rpc=secrets.token_hex(32)))
        cmd += [
            "-p",
            f"127.0.0.1::{c['health_port']}",
            "-v",
            f"{tmp / 'garage.toml'}:/etc/garage.toml",
        ]
    for k, v in c["env"].items():  # type: ignore[union-attr]
        cmd += ["-e", f"{k}={v}"]
    t0 = time.monotonic()
    _run(*cmd, str(c["image"]), *c["args"])  # type: ignore[misc]
    try:
        port = _run("docker", "port", name, str(c["port"])).splitlines()[0].rsplit(":", 1)[1]
        hport = port
        if cand == "garage":
            _garage_bootstrap(name)
            hport = (
                _run("docker", "port", name, str(c["health_port"]))
                .splitlines()[0]
                .rsplit(":", 1)[1]
            )
        health = f"http://127.0.0.1:{hport}{c['health']}"
        while not _healthy(health):
            if time.monotonic() - t0 > 60:
                logs = _run("docker", "logs", "--tail", "15", name)
                return f"{cand}: never healthy at {health}\n{logs}"
            time.sleep(0.25)
        startup = time.monotonic() - t0
        env = {
            **os.environ,
            "SPIKE_ENDPOINT": f"http://127.0.0.1:{port}",
            "SPIKE_KEY": key,
            "SPIKE_SECRET": secret,
            "PYTHONUTF8": "1",
        }
        res = subprocess.run(
            [sys.executable, __file__, "--pytest"],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        tail = "\n".join(res.stdout.strip().splitlines()[-3:])
        return f"{cand}: healthy in {startup:.1f}s; pytest rc={res.returncode}\n{tail}"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _pytest_mode() -> int:
    """Swap the conftest fixture for one yielding the running endpoint, then run the tests."""
    sys.path.insert(0, str(ROOT))
    from collections.abc import Generator

    import pytest
    import s3fs

    import tests.integration.conftest as cf

    endpoint, key, secret = (os.environ[k] for k in ("SPIKE_ENDPOINT", "SPIKE_KEY", "SPIKE_SECRET"))

    @pytest.fixture(scope="session")
    def s3_storage_uri() -> Generator[str, None, None]:
        fs = s3fs.S3FileSystem(
            key=key,
            secret=secret,
            endpoint_url=endpoint,
            client_kwargs={"region_name": "us-east-1"},
        )
        fs.mkdir(BUCKET)
        s3fs.S3FileSystem.clear_instance_cache()
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": key,
                "AWS_SECRET_ACCESS_KEY": secret,
                "AWS_ENDPOINT_URL": endpoint,
                "AWS_DEFAULT_REGION": "us-east-1",
            }
        )
        yield f"s3://{BUCKET}/gflow/"

    cf.s3_storage_uri = s3_storage_uri  # pytest reuses this module from sys.modules
    return pytest.main(
        [
            "-m",
            "containers",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=tmp/bmin-spike",
            "tests/integration/test_storage_s3.py",
        ]
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--pytest"]:
        sys.exit(_pytest_mode())
    for cand in sys.argv[1:] or list(CANDIDATES):
        print(measure(cand), flush=True)
