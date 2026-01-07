# P2P File Transfer Protocol

ShardSync is a symmetric Peer-to-Peer (P2P) file distribution system implemented in Python. It demonstrates the core principles of decentralized networks, including file fragmentation, swarm-based downloading, and concurrent socket management.

Unlike client-server architectures, ShardSync operates on a distributed model where every node functions simultaneously as a server (seeding blocks) and a client (leeching blocks).

![Project Status](https://img.shields.io/badge/status-closed-success)
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)

---

## Key Features

* **Block-Based Fragmentation:** Files are split into fixed-size chunks (1 KB blocks), allowing for non-linear, out-of-order downloading.
* **Symmetric Architecture:** Every peer implements a hybrid Client/Server model using multi-threading.
* **Swarm Distribution:** Leechers can download blocks from multiple neighbors simultaneously to maximize throughput.
* **Thread Safety:** Implements `Mutex` locks (`threading.Lock`) to manage concurrent read/write access to the file system and internal state.
* **Data Integrity:** Automatic SHA-256 cryptographic hashing to verify that the reassembled file matches the original source.
* **Custom Application Protocol:** Built upon raw TCP Sockets using a custom text-based protocol for block retrieval.

---

## Technical Architecture

### The Protocol
Communication between peers relies on a lightweight, stateless TCP protocol.
1.  **Request:** The client establishes a connection and sends `GET <block_index>`.
2.  **Response:** The server validates ownership of the block and streams the raw bytes.
3.  **Teardown:** The connection is closed immediately after the block transfer to free up resources.

### The Peer Lifecycle
1.  **Initialization:** The peer binds to a socket and calculates the file metadata (hash/block count).
2.  **Seeding (Server Thread):** A daemon thread listens for incoming TCP connections. Upon receiving a valid request, it reads the specific offset from the disk and sends the data.
3.  **Leeching (Client Thread):** If the peer does not have the complete file:
    * It identifies missing blocks.
    * It selects a random target block (rarest-first strategy simulation).
    * It connects to a random neighbor to request the data.
    * Upon successful download, the block is immediately available for seeding to other peers.

---

## Installation & Usage

### Prerequisites
* Python 3.8 or higher.
* No external dependencies are required (uses standard library only).

### Running the Simulation
The codebase includes a self-contained test environment that spawns local peers to simulate a network swarm.

1.  Clone the repository:
    ```bash
    git clone [https://github.com/gbernalle/shard-sync.git](https://github.com/gbernalle/shard-sync.git)
    cd shard-sync
    ```

2.  Run the main script:
    ```bash
    python peer_to_peer.py
    ```

### Expected Output
The script will:
1.  Generate a random binary file (`file_B_original.txt`).
2.  Initialize 1 Seeder (Port 5000) and 2 Leechers (Ports 5001, 5002).
3.  Display real-time logs of the block exchange process.
4.  Perform a final SHA-256 verification to ensure data consistency.

```text
[Peer 5000]: Server listening on localhost:5000
[Peer 5001 Client]: Starting download...
[Peer 5001]: Downloaded Block 42 from 5000. Progress: 1/1024 blocks.
...
[Peer 5001 Client]: DOWNLOAD COMPLETE! File reassembled.
  SUCCESS: SHA-256 Hash matches!