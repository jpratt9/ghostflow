# Spike — replacing the deleted MinIO image in the S3 container tests

**Date:** 2026-10-19 · **Cost:** $0, local Docker 28.3 only · **Probe:**
`scripts/dev/spike_s3_test_backend.py` (readings pre-registered in its docstring) ·
**Tests run:** the real `tests/integration/test_storage_s3.py` (8 tests) per candidate.

## Question

`tests/integration/constants.py` pinned `minio/minio:RELEASE.2024-06-13T22-53-53Z`.
Measured today: that tag and `minio/minio:latest` answer `denied: requested access to the
resource is denied`; `quay.io/minio/minio:RELEASE.2024-06-13T22-53-53Z` answers `no such
manifest`. MinIO stopped publishing community images in Oct 2025 and removed them from
Docker Hub in Sep 2026. No CI job ran `-m containers`, so nothing noticed. Which server
replaces it with the smallest fixture change?

## Result

| Candidate | Resolves | Pinnable | License | Maintenance signal | Tests | Fixture change | Healthy in |
|---|---|---|---|---|---|---|---|
| `cgr.dev/chainguard/minio` | yes (`:latest` only) | **digest only**: the free tier serves no version tags (`:RELEASE.2026-09-22T19-25-18Z` → `MANIFEST_UNKNOWN`) | AGPL-3.0 (MinIO server) | rebuilt daily from source; image created 2026-10-19, `minio version RELEASE.2026-09-22T19-25-18Z` | 8/8 | none: entrypoint `/usr/bin/minio`, same `server /data`, `MINIO_ROOT_*`, `/minio/health/live` | 6.0 s |
| `rustfs/rustfs:1.0.3` | yes | **tag + digest** (`sha256:9ca95595…688b`, index) | Apache-2.0 | 1.0.3 released 2026-10-17; 1.0.2 on 10-16; preview tags almost daily | 8/8 | env names `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`, health `/health`, no command (entrypoint defaults to `/data`) | 2.0 s |
| `dxflrs/garage:v2.4.1` | yes | tag + digest | AGPL-3.0 | v2.4.1 2026-09-08; commit-SHA tags daily | 8/8 | **heavy**: mounted `garage.toml` (rpc secret, region), `layout assign` + `layout apply`, `key import` with a `GK…` id, `key allow --create-bucket` via `docker exec` | 5.4 s (bootstrap included) |

Pre-registered reading applied: all three are N/N. Garage needs a CLI bootstrap, so it loses to a
drop-in. Chainguard is the only zero-change drop-in, but it cannot be pinned to a version, only
to a digest of a floating `latest`. The free tier does not promise to keep old digests, which
is the failure mode we are escaping.

## Decision

**RustFS 1.0.3, pinned by tag and digest.** The fixture change is three lines (two env names
and the health path). Its license is Apache-2.0, and it publishes versioned tags we can hold.
The identifiers `minio_*` / `MINIO_*` became `s3_*` / `S3_*`, because the backend is no longer
MinIO. The `docker-compose.yml` local stack moved to the same image; its health check (`curl
/health`) and console on `:9001` (`RUSTFS_CONSOLE_ENABLE=true`) were checked with `docker
compose up` (healthy, console 200).

## Not measured

- Whether Chainguard keeps old free-tier digests pullable over time. This was not tested;
  it did not decide the choice, because RustFS publishes versioned tags either way.
- RustFS behaviour beyond what our 8 tests exercise (multipart, versioning, presigned URLs).
  gflow uses none of these through s3fs today.
- A RustFS 1.0.x release is days old. If a later tag regresses, the pin holds us on 1.0.3. The new
  `storage-containers` CI job turns the build red if the pinned image disappears.
