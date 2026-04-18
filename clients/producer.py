import json
import time
import random

# IMport the Confluent Kafka producer
from confluent_kafka import Producer


# -----CONFIGURATION-----
config = {
    "bootstrap.servers": "localhost:9094",
    "client.id": "python-producer-2",
    # Reliability
    "acks": "all",
    "enable.idempotence": True,
    "retries": 5,
    "max.in.flight.requests.per.connection": 1,
    # performnce
    "linger.ms": 20,
}


# -----CREATE PRODUCER-----
producer = Producer(config)

topic = "clickstream_events"


# -----DELIVERY REPORT-----
def delivery_report(err, msg):
    if err is not None:
        print(f"DELIVERY FAILED: {err}")
    else:
        print(
            f'Delivered to "{msg.topic()}" [partition {msg.partition()}] @ offset {msg.offset()}'
        )


clickstream_data = [
    {"user_id": "user-1", "event": "page_view", "page": "/products"},
    {"user_id": "user-2", "event": "page_view", "page": "/home"},
    {"user_id": "user-1", "event": "add_to_cart", "product_id": "prod-123"},
    {"user_id": "user-3", "event": "search", "query": "kafka python"},
    {"user_id": "user-2", "event": "purchase", "order_id": "ord-456"},
    {"user_id": "user-1", "event": "logout"},
]

print("Starting to produce messages...")
for i in range(200):
    data = random.choice(clickstream_data)
    data["timestamp"] = time.time()

    key = data["user_id"]
    value = json.dumps(data)

    producer.produce(
        topic,
        key=key.encode("utf-8"),
        value=value.encode("utf-8"),
        callback=delivery_report,
    )

    producer.poll(0)
    time.sleep(1.5)

print("\nFlushing... waiting for all acknowledgements.")
remaining = producer.flush(timeout=10)
if remaining > 0:
    print(f"WARNING: {remaining} messages were NOT delivered!")
else:
    print("All messages successfully produced.")
