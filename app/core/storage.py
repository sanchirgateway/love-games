"""Хранилище файлов (SeaweedFS по S3 API)."""

from typing import Any

import aioboto3
from botocore.config import Config

from config.config import s3_settings

_session = aioboto3.Session()
# path-style обязателен: иначе клиент пойдёт на <bucket>.<host> и адрес не резолвится
_config = Config(s3={"addressing_style": "path"}, signature_version="s3v4")


def _client() -> Any:
    return _session.client(
        "s3",
        endpoint_url=s3_settings.endpoint,
        aws_access_key_id=s3_settings.access_key,
        aws_secret_access_key=s3_settings.secret_key,
        region_name="us-east-1",  # SeaweedFS регион не важен, но boto требует
        config=_config,
    )


async def upload(key: str, data: bytes, content_type: str) -> None:
    async with _client() as s3:
        await s3.put_object(Bucket=s3_settings.bucket, Key=key, Body=data, ContentType=content_type)


async def download(key: str) -> bytes:
    async with _client() as s3:
        obj = await s3.get_object(Bucket=s3_settings.bucket, Key=key)
        async with obj["Body"] as body:
            return await body.read()


async def delete(key: str) -> None:
    async with _client() as s3:
        await s3.delete_object(Bucket=s3_settings.bucket, Key=key)
