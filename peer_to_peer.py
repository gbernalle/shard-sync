import socket
import threading
import os
import math
import hashlib
import time
import random
import shutil

BLOCK_SIZE = 1024
HOST = 'localhost'

class Peer:
    def __init__(self, port: int, neighbors: list, file_path: str,
                 file_hash: str, total_blocks: int, is_seeder: bool = False):
        self.host = HOST
        self.port = port
        self.neighbors = neighbors
        self.file_path = file_path
        self.file_hash = file_hash
        self.total_blocks = total_blocks
        self.is_seeder = is_seeder
        
        if is_seeder:
            self.owned_blocks = set(range(self.total_blocks))
        else:
            self.owned_blocks = set()

        self.lock = threading.Lock()
        self.running = True

    def start(self):
        print(f"[Peer {self.port}]: Starting...")
        server_thread = threading.Thread(target=self.run_server, daemon=True)
        server_thread.start()
        print(f"[Peer {self.port}]: Server listening on {self.host}:{self.port}")

        if not self.is_seeder:
            time.sleep(1)
            download_thread = threading.Thread(target=self.run_download_loop, daemon=True)
            download_thread.start()

    def run_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)

        while self.running:
            try:
                conn, addr = server_socket.accept()
                handler_thread = threading.Thread(
                    target=self.handle_request,
                    args=(conn, addr),
                    daemon=True
                )
                handler_thread.start()
            except Exception as e:
                if self.running:
                    print(f"[Peer {self.port} Server]: Server error: {e}")

    def handle_request(self, conn: socket.socket, addr):
        try:
            request = conn.recv(1024).decode().strip()
            if request.startswith('GET'):
                try:
                    block_index = int(request.split(' ')[1])
                except (IndexError, ValueError):
                    return

                with self.lock:
                    has_block = block_index in self.owned_blocks

                if has_block:
                    block_data = self._read_block(block_index)
                    conn.sendall(block_data)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"[Peer {self.port} Server]: Error handling client {addr}: {e}")
        finally:
            conn.close()

    def run_download_loop(self):
        print(f"[Peer {self.port} Client]: Starting download...")

        while len(self.owned_blocks) < self.total_blocks:
            needed_blocks = set(range(self.total_blocks)) - self.owned_blocks
            if not needed_blocks:
                break

            target_block = random.choice(list(needed_blocks))
            shuffled_neighbors = list(self.neighbors)
            random.shuffle(shuffled_neighbors)

            success = False
            for neighbor_host, neighbor_port in shuffled_neighbors:
                if self.download_block(target_block, (neighbor_host, neighbor_port)):
                    success = True
                    break

            if not success:
                time.sleep(0.1)

        print(f"\n[Peer {self.port} Client]: DOWNLOAD COMPLETE! File reassembled.\n")
        self.running = False

    def download_block(self, block_index: int, neighbor_addr: tuple) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(neighbor_addr)

            request = f"GET {block_index}\n"
            sock.sendall(request.encode())

            block_data = b''
            while True:
                chunk = sock.recv(BLOCK_SIZE)
                if not chunk:
                    break
                block_data += chunk

            sock.close()

            if 0 < len(block_data) <= BLOCK_SIZE:
                self._write_block(block_index, block_data)
                with self.lock:
                    self.owned_blocks.add(block_index)

                print(f"[Peer {self.port}]: Downloaded Block {block_index} from {neighbor_addr[1]}. "
                      f"Progress: {len(self.owned_blocks)}/{self.total_blocks} blocks.")
                return True

        except (socket.timeout, ConnectionRefusedError, ConnectionAbortedError):
            pass
        except Exception as e:
            print(f"[Peer {self.port}]: Error downloading block {block_index}: {e}")

        return False

    def _read_block(self, block_index: int) -> bytes:
        offset = block_index * BLOCK_SIZE
        with self.lock:
            with open(self.file_path, 'rb') as f:
                f.seek(offset)
                return f.read(BLOCK_SIZE)

    def _write_block(self, block_index: int, data: bytes):
        offset = block_index * BLOCK_SIZE
        with self.lock:
            with open(self.file_path, 'r+b') as f:
                f.seek(offset)
                f.write(data)

def create_random_file(filename: str, size_kb: int):
    print(f"Creating test file '{filename}' with {size_kb} KB...")
    with open(filename, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))

def allocate_file_space(filename: str, total_size: int):
    print(f"Allocating space for '{filename}' with {total_size} bytes.")
    with open(filename, 'wb') as f:
        f.truncate(total_size)

def get_file_metadata(filename: str) -> dict:
    file_size = os.path.getsize(filename)
    total_blocks = math.ceil(file_size / BLOCK_SIZE)

    sha256 = hashlib.sha256()
    with open(filename, 'rb') as f:
        while chunk := f.read(BLOCK_SIZE):
            sha256.update(chunk)

    return {
        "hash": sha256.hexdigest(),
        "file_size": file_size,
        "total_blocks": total_blocks
    }

def verify_file_integrity(filename: str, original_hash: str) -> bool:
    print(f"Verifying integrity of '{filename}'...")
    if not os.path.exists(filename):
        print("  ERROR: File not found.")
        return False

    metadata = get_file_metadata(filename)

    if metadata["hash"] == original_hash:
        print(f"  SUCCESS: SHA-256 Hash matches! (Size: {metadata['file_size']} bytes)")
        return True
    else:
        print(f"  FAILURE: Hash mismatch.")
        print(f"    Expected: {original_hash}")
        print(f"    Received: {metadata['hash']}")
        return False

if __name__ == "__main__":
    TEST_FILENAME = "file_B_original.txt"
    TEST_FILE_SIZE_KB = 1024
    TEST_DIR = "test_env"

    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)

    original_file_path = os.path.join(TEST_DIR, TEST_FILENAME)
    create_random_file(original_file_path, TEST_FILE_SIZE_KB)

    metadata = get_file_metadata(original_file_path)

    print("\n--- Original File Metadata ---")
    print(f"  File:   {TEST_FILENAME}")
    print(f"  Size:   {metadata['file_size']} bytes")
    print(f"  Blocks: {metadata['total_blocks']} (of {BLOCK_SIZE} bytes)")
    print(f"  Hash:   {metadata['hash']}")
    print("-" * 37 + "\n")

    peer_configs = [
        {'port': 5001, 'neighbors': [(HOST, 5000), (HOST, 5002)], 'is_seeder': False},
        {'port': 5002, 'neighbors': [(HOST, 5000), (HOST, 5001)], 'is_seeder': False},
        {'port': 5000, 'neighbors': [(HOST, 5001), (HOST, 5002)], 'is_seeder': True},
    ]

    peers = []

    for config in peer_configs:
        port = config['port']
        peer_file_path = os.path.join(TEST_DIR, f"file_B_peer_{port}.txt")

        if config['is_seeder']:
            shutil.copy(original_file_path, peer_file_path)
        else:
            allocate_file_space(peer_file_path, metadata['file_size'])

        peer = Peer(
            port=port,
            neighbors=config['neighbors'],
            file_path=peer_file_path,
            file_hash=metadata['hash'],
            total_blocks=metadata['total_blocks'],
            is_seeder=config['is_seeder']
        )
        peers.append(peer)
        peer.start()

    print("\n--- P2P Simulation Started (1 Seeder, 2 Leechers) ---")
    print("Waiting for leechers to complete download...\n")

    try:
        while True:
            time.sleep(2)
            all_done = True
            for p in peers:
                if not p.is_seeder and p.running:
                    all_done = False
                    break
            if all_done:
                print("\n--- Simulation Finished ---")
                break
    except KeyboardInterrupt:
        print("\nSimulation interrupted.")
        for p in peers:
            p.running = False

    print("\n--- Final File Verification ---")
    for p in peers:
        if not p.is_seeder:
            verify_file_integrity(p.file_path, metadata['hash'])

    print("\nCleaning up test environment...")
    print("Done.")