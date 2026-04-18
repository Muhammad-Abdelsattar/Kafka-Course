import json
import time
from confluent_kafka import Consumer, KafkaException, KafkaError


# --- Configuration ---
conf = {
    "bootstrap.servers": "localhost:9094",
    "group.id": "clickstream-processing-group-1",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
}

# --- Create Consumer and Subscribe ---
consumer = Consumer(conf)

topic = "clickstream_events"
consumer.subscribe([topic])
print(f"Subscribed to '{topic}'. Waiting for messages...")

# --- Poll Loop ---
try:
    while True:
        msg = consumer.poll(timeout=1.0)

        # No message received within timeout
        if msg is None:
            continue

        # Handle errors
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print(f"Reached end of partition {msg.topic()} [{msg.partition()}]")
            else:
                raise KafkaException(msg.error())
        else:
            # --- Process the message ---
            user_id = msg.key().decode("utf-8")
            event_data = json.loads(msg.value().decode("utf-8"))

            print(
                f"Received: user={user_id} "
                f"| event={event_data['event']} "
                f"| partition={msg.partition()} "
                f"| offset={msg.offset()}"
            )

            # Simulate processing work
            time.sleep(0.1)

            # Commit AFTER successful processing (at-least-once)
            consumer.commit(asynchronous=False)

# --- Graceful Shutdown ---
except KeyboardInterrupt:
    print("\nShutting down...")
finally:
    print("Closing consumer.")
    consumer.close()
