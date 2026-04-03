import io
from pathlib import PurePosixPath

import boto3
import structlog
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class StorageService:
    """S3-compatible object storage for documents."""

    def __init__(self):
        settings = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
        self._bucket = settings.s3_bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self._bucket)
                logger.info("bucket_created", bucket=self._bucket)
            except ClientError as e:
                logger.warning("bucket_creation_failed", error=str(e))

    async def upload_file(self, content: bytes, key: str, content_type: str | None = None) -> str:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self._client.upload_fileobj(
            io.BytesIO(content),
            self._bucket,
            key,
            ExtraArgs=extra_args,
        )
        logger.info("file_uploaded", key=key, size=len(content))
        return key

    async def download_file(self, key: str) -> bytes:
        buffer = io.BytesIO()
        self._client.download_fileobj(self._bucket, key, buffer)
        buffer.seek(0)
        return buffer.read()

    async def delete_file(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
        logger.info("file_deleted", key=key)

    async def get_presigned_url(self, key: str, expiration: int = 3600) -> str:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiration,
        )
        return url

    async def file_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False
