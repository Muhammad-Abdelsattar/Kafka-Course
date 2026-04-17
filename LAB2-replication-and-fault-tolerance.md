# Lab 2: Replication & Fault Tolerance (3-Broker Cluster)

## Objective

Understand how replication protects data, observe automatic failover when a
broker dies, and learn what `min.insync.replicas` controls.

---

## Step 0 - Start the Cluster

```bash
docker compose -f docker/muliple_brokers/docker-compose.yml up -d
```

Wait ~30 seconds, then verify all three brokers and the UI are running:

```bash
docker compose -f docker/muliple_brokers/docker-compose.yml ps
```

Open **<http://localhost:12000>** and confirm 3 brokers appear.

> Commands run inside **kafka-1** unless stated otherwise.
> Open **two terminals** (or split your terminal) - you will need them.

---

## Step 1 - Inspect the KRaft Quorum

KRaft replaced ZooKeeper for metadata management. This command shows who is
the active controller and which nodes are voters:

```bash
docker exec -it kafka-1 kafka-metadata-quorum.sh \
  --bootstrap-server localhost:9092 \
  describe --status
```

Note which node is the controller leader.

You most likely don't understand this yet. Don't worry about this for now. Just make sure it works with no errors.

---

## Step 2 - Create Topics with Different Replication Factors

```bash
# RF 3 - every partition copied to all 3 brokers
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic rf-3-topic --partitions 3 --replication-factor 3

# RF 1 - no replication at all
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic rf-1-topic --partitions 3 --replication-factor 1
```

Describe both:

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-3-topic

docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-1-topic
```

Key columns to understand:

| Column       | Meaning                                             |
| ------------ | --------------------------------------------------- |
| **Leader**   | Broker handling reads/writes for this partition     |
| **Replicas** | Brokers _assigned_ to hold a copy (desired state)   |
| **Isr**      | Brokers that are actually caught up (current state) |

Compare the Replicas column: RF 3 shows 3 broker IDs per partition; RF 1 shows only 1.

---

## Step 3 - Produce Data

Load data into both topics so we can test what happens during a failure.

**Terminal 1 - produce to `rf-3-topic`:**

```bash
docker exec -it kafka-1 kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-3-topic \
  --property "parse.key=true" \
  --property "key.separator=:"
```

```
sensor-1:temperature=22.5
sensor-2:temperature=19.8
sensor-3:temperature=25.1
sensor-1:temperature=23.0
sensor-2:temperature=20.1
```

**Ctrl + C**, then produce to `rf-1-topic`:

```bash
docker exec -it kafka-1 kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-1-topic \
  --property "parse.key=true" \
  --property "key.separator=:"
```

```
critical-1:important data A
critical-2:important data B
critical-3:important data C
```

**Ctrl + C**.

---

## Step 4 - Snapshot Before Failure

Record the current leader assignments so you can compare after the crash:

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-3-topic
```

Write down the Leader for partitions 0, 1, 2 **in a separate notepad, you will need that**.

---

## Step 5 - Kill a Broker

```bash
docker stop kafka-2
```

Wait ~10 seconds, then describe both topics:

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-3-topic
```

**Observe:**

- **Leader** - partitions that had broker 2 as leader now have a new leader.
- **Isr** - broker 2 is gone (it's not caught up because it's dead).
- **Replicas** - broker 2 is still listed (this is the desired config, not the current reality, so that's just a configuration the cluster tries to reach, but doesn't mean it's actually caught up).

**The data in the partitions of broker 2 are still there, since we have other 2 replicas of that partition.**

Now check `rf-1-topic`:

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-1-topic
```

Partitions whose only replica was broker 2 now have **no leader**. Interesting, right?

In this case, the data for all the partitions in broker 2 is lost. **That's why replication is extremely important. It's the key to fault tolerance.**

---

## Step 6 - Test Data Availability

**Terminal 2 - read from `rf-3-topic`:**

```bash
docker exec -it kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-3-topic \
  --from-beginning \
  --property print.key=true
```

✅ All messages are intact - replication saved the data.

**Try reading from `rf-1-topic`:**

```bash
docker exec -it kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-1-topic \
  --from-beginning
```

❌ Partitions owned by the dead broker are unreachable.

**Still in Terminal 1 - produce new records while broker 2 is down:**

```bash
docker exec -it kafka-1 kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-3-topic \
  --property "parse.key=true" \
  --property "key.separator=:"
```

```
sensor-1:produced during failure
```

**Ctrl + C**. The cluster keeps working on 2/3 brokers.

---

## Step 7 - Recover the Broker

```bash
docker start kafka-2
```

Describe the topic instantly after starting the broker, you may not see borker 2 in the ISR column yet, that's expected, because to be in ISR, a broker needs to have caught up with the new leader.

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-3-topic
```

Wait ~20 seconds, then verify broker 2 is back in ISR:

```bash
docker exec -it kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic rf-3-topic
```

Broker 2 should reappear in the Isr column once it has caught up.

---

## Step 8 - `min.insync.replicas`

This setting defines **how many replicas must acknowledge a write** when the producer uses `acks=all`. It's the knob between durability and availability.

```bash
docker exec -it kafka-1 kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --entity-type topics \
  --entity-name rf-3-topic \
  --add-config min.insync.replicas=2
```

**Test with 1 broker down (2 ISR remain - meets min-ISR):**

```bash
docker stop kafka-3
```

```bash
docker exec -it kafka-1 kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic rf-3-topic \
  --producer-property acks=all \
  --property "parse.key=true" \
  --property "key.separator=:"
```

```
sensor-1:works with 2 ISR
```

✅ Write succeeds.

**Test with 2 brokers down (1 ISR remains - below min-ISR):**

```bash
docker stop kafka-2
```

Try the same producer command and type a message.

❌ Kafka **refuses the write** because it cannot guarantee the record is
replicated to 2 nodes.

Recover:

```bash
docker start kafka-2 kafka-3
```

---

## Step 10 - Explore in Kafka UI

Open **<http://localhost:12000>** and browse:

- **Brokers** - partition/leader distribution
- **Topics → rf-3-topic → Messages** - records with keys, offsets, partitions
- **Topics → rf-3-topic → Settings** - find `min.insync.replicas`

---

## Step 11 - Clean Up

```bash
docker compose -f docker/muliple_brokers/docker-compose.yml down -v
```

---

## Summary

| Concept                 | Key Point                                              |
| ----------------------- | ------------------------------------------------------ |
| **Replication**         | Copies data across brokers; survives failures          |
| **Leader / ISR**        | Leader handles I/O; ISR = replicas that are caught up  |
| **Failover**            | A new leader is auto-elected from the ISR              |
| **RF 1 vs RF 3**        | RF 1 = no safety net; RF 3 = survives 1 broker failure |
| **min.insync.replicas** | Minimum replicas that must ack a write (`acks=all`)    |
