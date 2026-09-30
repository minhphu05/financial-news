"""Provider-specific Spark filesystem configuration.

Delta transformations call this boundary once while constructing Spark.  Phase
06 ships only the local S3A runtime; the future ADLS profile is syntax checked but
does not pretend that the Hadoop ABFS connector or Azure credentials are present.
"""

from src.news_pipeline.config import Settings


def configure_storage(builder, settings: Settings):
    settings.validate()
    if settings.storage_provider != "s3":
        raise ValueError(
            "Spark ADLS execution is not installed in the local release. Phase 07 must add "
            "the Hadoop Azure connector and authentication adapter."
        )
    endpoint = settings.endpoint.removesuffix("/")
    return (
        builder
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.access.key", settings.access_key)
        .config("spark.hadoop.fs.s3a.secret.key", settings.secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            str(endpoint.startswith("https://")).lower(),
        )
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )
        .config("spark.delta.logStore.class", "io.delta.storage.S3SingleDriverLogStore")
    )
