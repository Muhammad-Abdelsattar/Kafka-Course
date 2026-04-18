import json
import time
from confluent_kafka import Consumer, KafkaException


# Configuration
conf = {
    "bootstrap.servers": "localhost:9094",
    "group.id": "clickstream-batch-group-1",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
}

# Create Consumer  
consumer = Consumer(conf)
consumer.subscribe(["clickstream_events"])
print("Consuming in batches...")

# Batch Poll Loop 
try:
    while True:
        messages = consumer.consume(num_messages=100, timeout=5.0)

        # No messages received within timeout
        if not messages:
            print("No messages in the last 5 seconds...")
            continue

        print(f"\nGot a batch of {len(messages)} messages.")

        # Filter out errors, collect valid records
        valid_records = []
        for msg in messages:
            if msg.error():
                print(f"  Skipping error: {msg.error()}")
                continue

            user_id = msg.key().decode("utf-8")
            event_data = json.loads(msg.value().decode("utf-8"))
            valid_records.append(event_data)

            print(
                f"  user={user_id} "
                f"| event={event_data['event']} "
                f"| partition={msg.partition()} "
                f"| offset={msg.offset()}"
            )

        # Process the entire batch, then commit once
        if valid_records:
            print(f"  Processing {len(valid_records)} records...")
            time.sleep(0.5)  # Simulate bulk processing
            print(f"  Done.")

            consumer.commit(asynchronous=False)

# Graceful Shutdown 
except KeyboardInterrupt:
    print("\nShutting down...")
finally:
    print("Closing consumer.")
    consumer.close()
