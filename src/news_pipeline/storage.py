"""Small object-storage interface; transformations do not depend on boto3."""

from typing import Protocol

from .config import Settings


class ObjectStore(Protocol):
    def ensure_bucket(self) -> None: ...
    def exists(self, key: str) -> bool: ...
    def upload_file(self, path: str, key: str) -> None: ...
    def put_bytes(self, key: str, body: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def list_keys(self, prefix: str) -> list[str]: ...


class S3ObjectStore:
    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config

        self.bucket = settings.bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise

    def upload_file(self, path: str, key: str) -> None:
        self.client.upload_file(path, self.bucket, key)

    def put_bytes(self, key: str, body: bytes, content_type: str = "application/json") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        return [item["Key"] for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix)
                for item in page.get("Contents", [])]
