# Kafka Producers and Consumers with `confluent-kafka`

## Setup

```bash
pip install confluent-kafka
```

---

## Part 1 - The Producer

### 1.1 Connection Configuration

```python
conf = {
    'bootstrap.servers': 'localhost:9094',
    'client.id': 'python-producer-1',
}
```

**`bootstrap.servers`** - The initial entry point to the Kafka cluster, not the full list of brokers. The bootstrap process works as follows:

1. **Initial connection:** The producer connects to the specified broker(s).
2. **Metadata request:** The producer asks that broker for the full cluster map - all brokers, all topics, and which broker leads which partition.
3. **Metadata response:** The broker returns the complete cluster topology.
4. **Direct connections:** The producer opens persistent TCP connections directly to the brokers that lead the partitions it needs to write to. The bootstrap broker's job is now done.

After the initial metadata request, the producer never depends on the bootstrap server again. It talks directly to whichever broker leads the partition it needs. These are long-lived TCP connections - opened once, reused for all messages. The producer only connects to brokers that lead partitions it writes to, not every broker in the cluster.

In production, list 2–3 brokers for fault tolerance:

```python
'bootstrap.servers': 'broker-1:9092,broker-2:9092,broker-3:9092'
```

The client tries each one until one responds. Only one needs to succeed - it returns the full cluster map. After that, the list is never used again.

**`client.id`** - A label that shows up in broker logs and monitoring dashboards. Helps identify which application is producing. Not functionally important, but very useful for debugging.

---

### 1.2 Reliability Configuration

```python
conf = {
    'bootstrap.servers': 'localhost:9094',
    'client.id': 'python-producer-1',
    'acks': 'all',
    'enable.idempotence': True,
    'retries': 5,
    'max.in.flight.requests.per.connection': 1,
}
```

**`acks`** - Controls how many brokers must confirm a write before it is considered successful. When a message is sent, the leader broker receives it and replicates it to follower brokers.

| Value      | Behavior                                          | Durability                                | Speed   |
| ---------- | ------------------------------------------------- | ----------------------------------------- | ------- |
| `acks=0`   | Don't wait for any confirmation. Fire and forget. | Data can be lost                          | Fastest |
| `acks=1`   | Wait for the leader only.                         | Lost if leader crashes before replicating | Medium  |
| `acks=all` | Wait for the leader AND all in-sync replicas.     | No data loss                              | Slowest |

For data pipelines, always use `acks='all'`. The speed difference is negligible compared to the cost of losing data.

**`enable.idempotence`** - Prevents duplicate messages caused by retries. Without idempotence, the following can happen: the producer sends a message, the broker writes it and sends back an ACK, but the ACK is lost on the network. The producer thinks it failed and retries. The broker writes the same message again — creating a duplicate.

With idempotence enabled, every producer gets a unique **Producer ID (PID)**, and every message gets a **sequence number**. If the broker sees the same PID + sequence number twice, it ignores the retry. This is especially important for data pipelines because duplicates corrupt data (e.g., double-counting a purchase event in analytics).

**`retries`** - If a send fails due to a transient issue (e.g., network hiccup), retry up to this many times before giving up.

**`max.in.flight.requests.per.connection`** - Controls how many unacknowledged requests can be in flight simultaneously to a single broker. If multiple requests are in flight and one fails and gets retried, messages can arrive out of order. Setting this to `1` guarantees strict ordering — only one unacknowledged request at a time. With idempotence enabled, you could technically go higher safely, but `1` is the safest default.

---

### 1.3 Performance Configuration

```python
conf = {
    'bootstrap.servers': 'localhost:9094',
    'client.id': 'python-producer-1',
    'acks': 'all',
    'enable.idempotence': True,
    'retries': 5,
    'max.in.flight.requests.per.connection': 1,
    'linger.ms': 20,
    'batch.size': 32768,
    'compression.type': 'snappy',
}
```

`produce()` does not immediately send a message over the network. It places the message into an internal buffer for batching. Instead of making one network round-trip per message, batching allows multiple messages to be sent together in a single round-trip - dramatically improving throughput.

**`linger.ms`** - After a message lands in the buffer, wait up to this many milliseconds to see if more messages come in, then send them all together as one batch. Higher values mean more batching and better throughput, but also more latency (messages sit in the buffer longer). For real-time dashboards, `linger.ms=5` may be appropriate. For overnight batch loads, `linger.ms=100` is fine.

**`batch.size`** - If the batch reaches this size (in bytes) before `linger.ms` expires, send it immediately. Whichever threshold hits first triggers the send.

**`compression.type`** - Compresses the entire batch before sending. Less data on the network. Options are `snappy`, `gzip`, `lz4`, `zstd`, or `none`. Snappy is the best general-purpose choice — fast with decent compression.

---

### 1.4 The Complete Internal Pipeline

When you call `produce()`, you are not talking to Kafka directly. You are dropping a message into a buffer. A background thread (managed by `librdkafka`) handles everything else:

1. **`produce()`** places the message into a per-partition internal buffer.
2. The **batching engine** groups messages according to `linger.ms` and `batch.size`.
3. The **compressor** compresses each batch (e.g., snappy).
4. The batch is sent to the appropriate **broker** (partition leader).
5. The broker sends back an ACK or error.
6. The **delivery report callback** fires when you call `poll()`.

Your code never blocks on network I/O. This is what makes the producer so fast.

---

### 1.5 Creating the Producer and Delivery Report

```python
producer = Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f'DELIVERY FAILED: {err}')
    else:
        print(f'Delivered to "{msg.topic()}" [partition {msg.partition()}] @ offset {msg.offset()}')
```

Since `produce()` is asynchronous (returns immediately), the delivery report callback is how you find out whether the message actually made it. On success, you get the topic, partition, and offset - proof of exactly where your message was written. On failure, you get the error.

These callbacks do not fire by themselves. They queue up internally, and you must call `poll()` to trigger them.

---

### 1.6 Producing Messages

```python
topic = 'clickstream_events'

clickstream_data = [
    {'user_id': 'user-1', 'event': 'page_view', 'page': '/products'},
    {'user_id': 'user-2', 'event': 'page_view', 'page': '/home'},
    {'user_id': 'user-1', 'event': 'add_to_cart', 'product_id': 'prod-123'},
    {'user_id': 'user-3', 'event': 'search', 'query': 'kafka python'},
    {'user_id': 'user-2', 'event': 'purchase', 'order_id': 'ord-456'},
    {'user_id': 'user-1', 'event': 'logout'},
]

print("Starting to produce messages...")
for i in range(20):
    data = random.choice(clickstream_data)
    data['timestamp'] = time.time()

    key = data['user_id']
    value = json.dumps(data)

    producer.produce(
        topic,
        key=key.encode('utf-8'),
        value=value.encode('utf-8'),
        callback=delivery_report
    )

    producer.poll(0)
    time.sleep(0.2)
```

**Key** - Using `user_id` as the message key ensures Kafka hashes the key to determine which partition the message goes to. All events from the same user land in the same partition, guaranteeing per-user ordering (e.g., `page_view` → `add_to_cart` → `purchase` in order).

**Encoding** - Both key and value must be bytes. Kafka just moves bytes around. JSON is used here for structure, encoded to UTF-8. In production you might use Avro or Protobuf.

**`produce()` is non-blocking** - It returns instantly. The message goes into the internal buffer and the actual sending happens on the background thread.

**`producer.poll(0)`** - Checks if any broker responses have arrived and triggers the corresponding delivery report callbacks. The `0` means don't wait — just process whatever's available right now and return. Best practice is to call `poll(0)` after every `produce()`, or at least periodically. If you never call `poll()`, the callback queue grows unboundedly, you never hear about failures, and eventually the internal buffer fills up.

---

### 1.7 Flush and Shutdown

```python
print("\nFlushing... waiting for all acknowledgements.")
remaining = producer.flush(timeout=10)
if remaining > 0:
    print(f"WARNING: {remaining} messages were NOT delivered!")
else:
    print("All messages successfully produced.")
```

**This is critical.** When your script ends, there may still be messages sitting in the internal buffer waiting to be batched and sent. If you let the script exit without flushing, those messages are gone - silent data loss with no error or warning.

`flush()` blocks until every buffered message has been sent and every delivery callback has been served. The `timeout` parameter sets the maximum wait time in seconds. It returns the number of messages still in the queue (should be zero).

Forgetting `flush()` is one of the most common causes of data loss in production.

---

## Part 2 - The Consumer

### 2.1 Imports

```python
import json
import time
from confluent_kafka import Consumer, KafkaException, KafkaError
```

`KafkaException` and `KafkaError` are imported for error handling in the poll loop.

---

### 2.2 Connection and Group Configuration

```python
conf = {
    'bootstrap.servers': 'localhost:9094',
    'group.id': 'clickstream-processing-group-1',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,
}
```

**`bootstrap.servers`** - Same entry point as the producer, but the consumer's startup is more involved:

1. Connect to the bootstrap broker and request metadata (same as producer).
2. Ask: "Who is the **Group Coordinator** for my group?" The broker responds with a specific broker.
3. Contact the Group Coordinator and request to join the consumer group.
4. The Group Coordinator runs **partition assignment** (potentially triggering a rebalance if other consumers are already in the group).
5. The consumer receives its assigned partitions, connects to their leaders, and begins fetching messages.

The extra steps compared to the producer exist because the consumer needs to **coordinate** with other consumers in the same group. A **Group Coordinator** is an ordinary broker that takes on the extra responsibility of managing one or more consumer groups.

---

**`group.id`** - The most important consumer setting. All consumers with the same `group.id` form a **consumer group**. Kafka automatically distributes partitions among group members. Each partition is assigned to exactly one consumer within the group at any given time. If a consumer dies, Kafka rebalances and assigns its partitions to surviving consumers.

Key behaviors:

- If there are more consumers than partitions, some consumers sit idle.
- If two different applications need to read the same topic independently, give them different `group.id`s. Each group gets its own copy of all messages with independent offsets.

---

**`auto.offset.reset`** - An **offset** is a position marker (like a bookmark) — the sequential number of the next message to read within a partition (0, 1, 2, 3...). This setting determines where to start reading when this consumer group reads a partition **for the very first time** and has no saved offset:

- `earliest` - Go back to the beginning, read everything.
- `latest` - Skip all existing data, only read new messages that arrive after you join.

For data pipelines, `earliest` is typical so you don't miss any data. **Important:** Once the consumer has committed an offset, this setting becomes irrelevant. The consumer always resumes from its last committed offset. This only applies to the very first read.

---

**`enable.auto.commit`** - Controls whether Kafka automatically commits offsets in the background. After reading and processing a message, you need to tell Kafka "I'm done with this one, move my bookmark forward" — this is called **committing the offset**.

With auto-commit (`True`), Kafka commits offsets every 5 seconds in the background. This is dangerous:

If auto-commit fires before your processing completes and then the consumer crashes, Kafka thinks you've processed the message (the offset was advanced), but you actually haven't. That message is lost - skipped permanently.

With manual commit (`False`), you explicitly commit only after successful processing. If you crash after processing but before committing, the consumer restarts from the last committed offset and re-processes the message. This results in a duplicate, but not data loss.

**Delivery semantics summary:**

| Semantics         | Meaning                     | How                            |
| ----------------- | --------------------------- | ------------------------------ |
| At-most-once      | May lose, never duplicate   | Auto-commit before processing  |
| **At-least-once** | Never lose, may duplicate   | Manual commit after processing |
| Exactly-once      | Never lose, never duplicate | Kafka Transactions (advanced)  |

**At-least-once with manual commit is the industry standard for data pipelines.** Duplicates are almost always preferable to data loss - you can design downstream systems to handle duplicates (idempotent writes, deduplication by unique ID, etc.) but you can't recover data you never processed.

---

### 2.3 Creating the Consumer and Subscribing

```python
consumer = Consumer(conf)

topic = 'clickstream_events'
consumer.subscribe([topic])
print(f"Subscribed to '{topic}'. Waiting for messages...")
```

`subscribe()` takes a list - you can subscribe to multiple topics at once. Behind the scenes, this triggers the group join process (contacting the Group Coordinator, joining the group, receiving partition assignments).

---

### 2.4 The Poll Loop

```python
try:
    while True:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print(f'Reached end of partition {msg.topic()} [{msg.partition()}]')
            else:
                raise KafkaException(msg.error())
        else:
            user_id = msg.key().decode('utf-8')
            event_data = json.loads(msg.value().decode('utf-8'))

            print(f"Received: user={user_id} | event={event_data['event']} "
                  f"| partition={msg.partition()} | offset={msg.offset()}")

            time.sleep(0.1)  # Simulate processing work

            consumer.commit(asynchronous=False)
```

**The `while True` loop** - A consumer is a long-lived process that continuously polls for new data, unlike a batch job that processes a file and exits.

**`consumer.poll(timeout=1.0)`** - Does several things at once:

1. Fetches records from the broker into an internal buffer (if the buffer is low).
2. Returns one message from that buffer to your code.
3. Sends **heartbeats** to the Group Coordinator ("I'm still alive").
4. Handles **rebalance events** (group membership changed, new partition assignments).

The `timeout=1.0` means: if there's nothing in the buffer, wait up to 1 second before returning `None`. If a message is available, it returns immediately.

**Heartbeat and liveness settings** - Because `poll()` is the heartbeat mechanism, you must call it frequently. If you stop calling `poll()` for too long, Kafka thinks you're dead. Three related settings control this behavior (we use the defaults, but they're important to understand):

| Setting                 | What It Controls                                                           | Default    |
| ----------------------- | -------------------------------------------------------------------------- | ---------- |
| `heartbeat.interval.ms` | How often `poll()` sends "I'm alive" signals                               | 3 seconds  |
| `session.timeout.ms`    | How long the coordinator waits with no heartbeat before declaring you dead | 45 seconds |
| `max.poll.interval.ms`  | Max time between two `poll()` calls before you're kicked out               | 5 minutes  |

`heartbeat.interval.ms` and `session.timeout.ms` catch **crashes** - the process dies, no more heartbeats, the coordinator notices after the timeout. `max.poll.interval.ms` catches a different problem — the consumer is alive but stuck (deadlock, slow database query). Heartbeats may still be going, but if `poll()` isn't called within 5 minutes, Kafka kicks the consumer out.

**Error handling** - `PARTITION_EOF` is not a real error; it means you've read all currently available messages in that partition. More will come later. Any other error (broker unreachable, authorization failure, etc.) is a real problem and should be raised.

**Processing and commit order** - Read → process → commit. The offset is only committed after successful processing. `asynchronous=False` means we wait for the commit to be confirmed by the broker before moving on — slightly slower but safer. If processing throws an exception, the commit is skipped, and the message will be redelivered after a restart or rebalance (at-least-once guarantee).

---

### 2.5 Graceful Shutdown

```python
except KeyboardInterrupt:
    print("Shutting down...")
finally:
    print("Closing consumer.")
    consumer.close()
```

**`close()` is essential.** Without it, when the consumer process dies abruptly, the Group Coordinator doesn't know. It waits for `session.timeout.ms` (45 seconds by default) with no heartbeat, then declares the consumer dead and triggers a rebalance. During those 45 seconds, the orphaned partitions sit unprocessed.

With `close()`, the consumer immediately tells the Group Coordinator "I'm leaving the group." The rebalance triggers instantly and other consumers pick up the orphaned partitions with no delay.

Always put `close()` in a `finally` block so it runs regardless of how the program exits (normal completion, exception, or Ctrl+C). `session.timeout.ms` serves as a safety net for cases when `close()` can't be called (e.g., `kill -9`, power loss).

---

## Part 3 - Batch Consuming with `consume()`

An alternative to `poll()` for batch-oriented processing.

### 3.1 Configuration

```python
import json
import time
from confluent_kafka import Consumer, KafkaException

conf = {
    'bootstrap.servers': 'localhost:9094',
    'group.id': 'clickstream-batch-group-1',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,
}

consumer = Consumer(conf)
consumer.subscribe(['clickstream_events'])
```

Same setup as before - a different `group.id` so it reads independently from the single-message consumer.

---

### 3.2 The Batch Poll Loop

```python
try:
    while True:
        messages = consumer.consume(num_messages=100, timeout=5.0)

        if not messages:
            print("No messages in the last 5 seconds...")
            continue

        print(f"\nGot a batch of {len(messages)} messages.")

        valid_records = []
        for msg in messages:
            if msg.error():
                print(f"  Skipping error: {msg.error()}")
                continue
            valid_records.append(json.loads(msg.value().decode('utf-8')))

        if valid_records:
            print(f"  Processing {len(valid_records)} records...")
            time.sleep(0.5)  # Simulate bulk processing
            print(f"  Done.")

            consumer.commit(asynchronous=False)

except KeyboardInterrupt:
    pass
finally:
    consumer.close()
```

**`consume(num_messages, timeout)`** - Returns a list of messages instead of one at a time. It waits up to the timeout to gather up to `num_messages` messages, whichever comes first. Under the hood, `consume()` is just calling `poll()` in a loop — it's a convenience wrapper.

**When to use `consume()`:** When processing is naturally batch-oriented - bulk-inserting rows into a database, writing batches of records to Parquet files, sending batches to an API.

**Trade-off:** If you crash halfway through processing a batch, you haven't committed any of it. On restart, you re-process the entire batch. With `poll()` and per-message commits, you re-process at most one message.

**`poll()` vs `consume()` comparison:**

|                | `poll()`                         | `consume()`                |
| -------------- | -------------------------------- | -------------------------- |
| Returns        | One message                      | List of messages           |
| Control        | Fine-grained                     | Batch-level                |
| Best for       | General purpose, maximum control | Bulk inserts, aggregations |
| Recommendation | Default choice                   | Great for batch workloads  |

---

## Part 4 - Common Pitfalls and Experiments

### Experiment 1: Removing `flush()` from the Producer

If `flush()` is omitted, messages still in the internal buffer when the script exits are lost forever - silent data loss with no error or warning. **`flush()` is non-negotiable.**

### Experiment 2: Killing the Consumer Without `close()`

Without `close()`, killing the consumer abruptly causes a delay of up to `session.timeout.ms` (45 seconds) before Kafka reassigns the orphaned partitions. With `close()`, the rebalance is instant.

### Experiment 3: Changing `auto.offset.reset`

With a brand new `group.id` and `auto.offset.reset='latest'`, the consumer sees nothing until new messages are produced after it joins. With `earliest`, it reads everything from the beginning. Both are valid strategies depending on whether historical replay or real-time-only processing is needed.

### Experiment 4: Two Consumers in the Same Group

Running two consumers with the same `group.id` causes Kafka to split partitions between them. Each consumer gets different partitions. If one dies, the other picks up the orphaned partitions after a rebalance. If there are more consumers than partitions, the extras sit idle.

### Experiment 5: Observing Batching Behavior

With `linger.ms=0`, each message is sent individually - no batching. With `linger.ms=500`, the producer waits longer to gather messages, sending larger batches less frequently. Tune based on latency vs. throughput requirements.

---

## Part 5 - Summary

**Producer lifecycle:** Configure → Bootstrap (metadata request) → Connect to partition leaders → `produce()` into buffer → background thread batches & sends → delivery callbacks confirm success/failure → `flush()` before exit.

**Consumer lifecycle:** Configure → Bootstrap → Find Group Coordinator → Join group → Get partition assignments → Poll loop forever → process message → commit offset → `close()` cleanly on shutdown.

**Producer key principles:**

- Always use `acks='all'` and `enable.idempotence=True` for safety.
- Always use delivery report callbacks.
- **Always call `flush()` before exit.**

**Consumer key principles:**

- Always use manual commit (`enable.auto.commit=False`) - commit **after** processing.
- Call `poll()` frequently (it's your heartbeat).
- **Always call `close()` in a `finally` block.**

**The pattern:** Write safely, confirm delivery, process reliably, commit explicitly, shut down gracefully. Every step has a reason.
