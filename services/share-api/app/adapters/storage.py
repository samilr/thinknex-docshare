"""Almacenamiento de snapshots: direccionado por contenido (sha256/<hash>)."""

import contextlib
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class BlobStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def ping(self) -> bool: ...


def snapshot_key(sha256: str) -> str:
    return f"sha256/{sha256}"


class S3BlobStorage:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def ping(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except (ClientError, BotoCoreError):
            return False
        return True


class InMemoryBlobStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def ping(self) -> bool:
        return True


class GcsBlobStorage:
    """Cloud Storage con credenciales por ADC (cuenta de servicio de Cloud Run, sin llaves).

    El bucket lo crea Terraform (privado, uniform access, public access prevention).
    """

    def __init__(self, bucket: str) -> None:
        from google.cloud import storage  # import diferido: solo se requiere en GCP

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)

    def get(self, key: str) -> bytes:
        data: bytes = self._bucket.blob(key).download_as_bytes()
        return data

    def exists(self, key: str) -> bool:
        return bool(self._bucket.blob(key).exists())

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        with contextlib.suppress(NotFound):
            self._bucket.blob(key).delete()

    def ping(self) -> bool:
        try:
            # objects.list está incluido en roles/storage.objectAdmin (buckets.get no).
            next(iter(self._client.list_blobs(self._bucket, max_results=1)), None)
        except Exception:
            return False
        return True
