# Pinned Docker image tags — keep in sync with docker-compose.yml.
# Update both files together when upgrading the local dev environment.
# RustFS replaced MinIO here: MinIO deleted its community images from Docker Hub
# (Sep 2026), see docs/superpowers/spikes/2026-10-19-minio-replacement.md.
S3_IMAGE: str = (
    "rustfs/rustfs:1.0.3@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b"
)
FAKE_GCS_IMAGE: str = "fsouza/fake-gcs-server:1.49.3"

# Credentials — local dev / CI only; never use in production.
S3_ACCESS_KEY: str = "rustfsadmin"
S3_SECRET_KEY: str = "rustfsadmin"  # noqa: S105

# Bucket / prefix used for integration-test objects.
S3_BUCKET: str = "gflow-test"
GCS_BUCKET: str = "gflow-test"
STORAGE_PREFIX: str = "gflow/"
