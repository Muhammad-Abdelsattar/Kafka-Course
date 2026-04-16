# Lab 1: Kafka Basics (Single Broker)

## Objective

Create topics, understand partitions, produce messages with and without keys, and observe how offsets and partition assignment work.

---

## Step 0 — Start the Environment

```bash
docker compose up -d
docker compose ps
```

Open **<http://localhost:12000>** (Kafka UI) in your browser and keep it open.

> All commands run inside the `kafka` container via `docker exec -it kafka`.

---

## Step 1 — Verify the Broker

Quick health check — if the broker is reachable, this prints API version info:

```bash
docker exec -it kafka kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092 | head -5
```

Ignore the output, we just want to make sure the broker is running.

---

## Step 2 — Create Your First Topic

A **topic** is a named feed that holds records. We start with the simplest setup: **1 partition, 1 replica.**

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic my-first-topic \
  --partitions 1 \
  --replication-factor 1
```

Inspect it:

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic my-first-topic
```

The output shows **Leader**, **Replicas**, and **Isr** — on a single broker, they all point to the same node (becuase we only have one broker).

---

## Step 3 — Multiple Partitions

**Partitions** are the unit of parallelism. Splitting a topic into partitions lets multiple consumers read in parallel.

let's create a topic with 3 partitions and 1 replica.

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic multi-partition-topic \
  --partitions 3 \
  --replication-factor 1
```

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic multi-partition-topic
```

You should see 3 lines — one per partition.

---

## Step 4 — Invalid Replication Factor

You cannot have more replicas than brokers. Try it:

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic will-fail-topic \
  --partitions 2 \
  --replication-factor 3
```

Read the error and try to explain why this fails.

---

## Step 5 — Produce Messages Without Keys

Without a key, Kafka distributes records across partitions in a round-robin fashion.

```bash
docker exec -it kafka kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic multi-partition-topic
```

Type five messages (press Enter after each), then **Ctrl + C** to exit to interactive producer shell.

Now open a **second terminal** (or split your current one) and consume them:

```bash
docker exec -it kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic multi-partition-topic \
  --from-beginning
```

---

## Step 6 — Produce Messages With Keys

A **key** guarantees that all records sharing the same key go to the **same partition**, preserving order per key.

```bash
docker exec -it kafka kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic multi-partition-topic \
  --property "parse.key=true" \
  --property "key.separator=:"
```

Notice the key separator is `:`. That means the key is separated by `:` from the value.

Write the following messages one by one, pressing enter after each. This is a very simple example, but you can use any key you want.

```
user-alice:logged in
user-bob:logged in
user-alice:clicked buy
user-bob:viewed cart
user-alice:logged out
user-bob:checked out
```

**Ctrl + C**, then in your second terminal read each partition with keys printed:

```bash
docker exec -it kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic multi-partition-topic \
  --partition 0 \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true
```

do the same for `--partition 1` and `--partition 2`.

Confirm that all `user-alice` records are in the same partition, and all `user-bob` records are in the same partition.

---

## Step 7 — Offsets

Every record in a partition gets a sequential **offset** starting at 0.
Offsets are unique within a partition but not across partitions.

```bash
docker exec -it kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic multi-partition-topic \
  --partition 0 \
  --from-beginning \
  --property print.offset=true \
  --property print.key=true
```

Verify offsets are sequential (0, 1, 2 …).

Try the same for `--partition 1` and `--partition 2`. Verify offsets start at 0 in each partition.

---

## Step 8 — Topic Configuration

Each topic has tuneable settings like retention and segment size:

```bash
docker exec -it kafka kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name multi-partition-topic \
  --describe --all
```

Find `retention.ms` — how many days is the default?
Find `segment.bytes` — what is the default segment size?

---

## Step 9 — Alter & Delete Topics

Increase partitions:

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic my-first-topic \
  --partitions 4
```

Now try to decrease them to 2 — observe the error. Kafka can't shrink partitions because it would have to throw away data (makes sense, right?)

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic my-first-topic \
  --partitions 1
```

Delete a topic:

```bash
docker exec -it kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic my-first-topic
```

---

## Step 10 — Clean Up

```bash
docker compose down -v
```

---

## Summary

| Concept                | Key Point                                              |
| ---------------------- | ------------------------------------------------------ |
| **Topic**              | Named feed of records                                  |
| **Partition**          | Unit of parallelism; records are appended sequentially |
| **Offset**             | Sequential ID per record within a partition            |
| **Key**                | Same key → same partition → ordering guarantee         |
| **Replication Factor** | Cannot exceed the number of brokers                    |
