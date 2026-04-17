# Kafka Crash Course

## 📚 Labs

| Lab                                                | Topic                                           | Setup            |
| -------------------------------------------------- | ----------------------------------------------- | ---------------- |
| [Lab 1](./LAB1-Basics.md)                          | Kafka Basics: topics, partitions, keys, offsets | Single broker    |
| [Lab 2](./LAB2-replication-and-fault-tolerance.md) | Replication & Fault Tolerance                   | 3-broker cluster |

## 🚀 Quick Start

Clone this repo:

```bash
git clone https://github.com/Muhammad-Abdelsattar/Kafka-Course.git

# make sure you are in the cloned directory
cd Kafka-Course
```

### Lab 1 - Single Broker

```bash
# Start
docker compose -f docker/simple/docker-compose.yml up -d

# Open Kafka UI
open http://localhost:12000

# Follow along in LAB1-Basics.md
```

### Lab 2 - 3-Broker Cluster

```bash
# Start
docker compose -f docker/muliple_brokers/docker-compose.yml up -d

# Open Kafka UI
open http://localhost:12000

# Follow along in LAB2-replication-and-fault-tolerance.md
```

## 🧹 Cleanup

```bash
# Lab 1
docker compose -f docker/simple/docker-compose.yml down -v

# Lab 2
docker compose -f docker/muliple_brokers/docker-compose.yml down -v
```

## 📋 Requirements

- Docker & Docker Compose
- Terminal with `docker exec` support
- Web browser for Kafka UI

> 💡 All lab commands are designed to run via `docker exec` into the Kafka container. See each lab file for detailed step-by-step instructions.
