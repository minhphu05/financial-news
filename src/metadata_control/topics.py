"""Create and inspect compacted metadata CDC topics."""

from __future__ import annotations

import argparse
import json

from .config import MetadataSettings


def ensure_topics(settings: MetadataSettings) -> dict:
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    metadata = admin.list_topics(timeout=15)
    missing = [topic for topic in settings.data_topics if topic not in metadata.topics]
    if missing:
        futures = admin.create_topics([
            NewTopic(
                topic,
                num_partitions=1,
                replication_factor=1,
                config={"cleanup.policy": "compact", "delete.retention.ms": "86400000"},
            )
            for topic in missing
        ])
        for topic, future in futures.items():
            future.result(timeout=30)
    result = {"created": missing, "metadata_topics": list(settings.data_topics)}
    print(json.dumps(result, indent=2))
    return result


def list_topics(settings: MetadataSettings) -> dict:
    from confluent_kafka import Consumer, TopicPartition
    from confluent_kafka.admin import AdminClient, ConfigResource

    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    metadata = admin.list_topics(timeout=15)
    resources = [ConfigResource(ConfigResource.Type.TOPIC, topic) for topic in settings.data_topics]
    configs = admin.describe_configs(resources)
    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": "metadata-topic-inspector",
        "enable.auto.commit": False,
    })
    topic_details = {}
    try:
        for topic in settings.data_topics:
            resource = next(item for item in resources if item.name == topic)
            values = configs[resource].result(timeout=15)
            low, high = consumer.get_watermark_offsets(TopicPartition(topic, 0), timeout=15)
            topic_details[topic] = {
                "partitions": len(metadata.topics[topic].partitions),
                "cleanup_policy": values["cleanup.policy"].value,
                "partition_0_low_offset": low,
                "partition_0_high_offset": high,
            }
    finally:
        consumer.close()
    topics = {
        name: {"partitions": len(value.partitions)}
        for name, value in sorted(metadata.topics.items())
        if not name.startswith("__") and name not in topic_details
    }
    topics.update(topic_details)
    result = {"topics": dict(sorted(topics.items()))}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ensure", "list"))
    args = parser.parse_args()
    settings = MetadataSettings.from_env()
    (ensure_topics if args.command == "ensure" else list_topics)(settings)


if __name__ == "__main__":
    main()
