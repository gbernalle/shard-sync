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
    """
    Implementa o nó Peer-to-Peer simétrico.

    Cada Peer opera simultaneamente como:
    1.  Ouve por conexões e serve os blocos que possui
    2.  Conecta-se a vizinhos para baixar os blocos que não possui
    """
    def __init__(self, port: int, neighbors: list, file_path: str,
                 file_hash: str, total_blocks: int, is_seeder: bool = False):

        self.host = HOST
        self.port = port
        self.neighbors = neighbors  # Lista de tuplas (host, port)

        self.file_path = file_path
        self.file_hash = file_hash
        self.total_blocks = total_blocks

        self.is_seeder = is_seeder

        # Um 'set' para rastrear os índices dos blocos que este peer possui.
        if is_seeder:
            self.owned_blocks = set(range(self.total_blocks))
        else:
            self.owned_blocks = set()

        self.lock = threading.Lock()

        self.running = True

    def start(self):
        """Inicia os processos de servidor e cliente do Peer."""
        print(f"[Peer {self.port}]: Iniciando...")

        #  Inicia o lado Servidor em uma thread separada
        server_thread = threading.Thread(target=self.run_server, daemon=True)
        server_thread.start()
        print(f"[Peer {self.port}]: Servidor ouvindo em {self.host}:{self.port}")

        # Se for um Leecher, inicia o processo de download
        if not self.is_seeder:
            # Pausa para dar tempo aos servidores de iniciarem
            time.sleep(1)
            download_thread = threading.Thread(target=self.start_download, daemon=True)
            download_thread.start()

    def run_server(self):
        """
        Executa o loop do servidor, ouvindo por conexões de outros peers
        e respondendo a solicitações de blocos.
        """
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)

        while self.running:
            try:
                # Aceita uma nova conexão
                conn, addr = server_socket.accept()
                handler_thread = threading.Thread(
                    target=self.handle_client_request,
                    args=(conn, addr),
                    daemon=True
                )
                handler_thread.start()
            except Exception as e:
                if self.running:
                    print(f"[Peer {self.port} Server]: Erro no servidor: {e}")

    def handle_client_request(self, conn: socket.socket, addr):
        """
        Lida com uma única solicitação de um peer cliente.
        Protocolo simples: "GET <block_index>\n"
        """
        try:
            request = conn.recv(1024).decode().strip()

            if request.startswith('GET'):
                block_index = int(request.split(' ')[1])

                # Verifica se possui o bloco
                with self.lock:
                    has_block = block_index in self.owned_blocks

                if has_block:
                    # Se tiver, lê o bloco do disco e envia
                    block_data = self._read_block(block_index)
                    conn.sendall(block_data)
                    # print(f"[Peer {self.port} Server]: Bloco {block_index} enviado para {addr[1]}")
                else:
                    # Se não tiver, apenas fecha a conexão (ou envia DONT_HAVE)
                    # O cliente tratará uma resposta vazia como falha
                    pass

        except (ConnectionResetError, BrokenPipeError):
            # Normal se o cliente desconectar
            pass
        except Exception as e:
            print(f"[Peer {self.port} Server]: Erro ao lidar com cliente {addr}: {e}")
        finally:
            conn.close()

    def start_download(self):
        """
        Executa o loop do cliente, solicitando blocos faltantes
        dos vizinhos.
        """
        print(f"[Peer {self.port} Cliente]: Iniciando download...")

        # Loop principal de download
        while len(self.owned_blocks) < self.total_blocks:
            # Identifica os blocos necessários
            needed_blocks = set(range(self.total_blocks)) - self.owned_blocks

            if not needed_blocks:
                break # Download completo

            # Escolhe um bloco aleatoriamente para evitar sobrecarga
            block_to_get = random.choice(list(needed_blocks))

            # Embaralha os vizinhos para distribuir a carga
            shuffled_neighbors = list(self.neighbors)
            random.shuffle(shuffled_neighbors)

            block_acquired = False
            for neighbor_host, neighbor_port in shuffled_neighbors:
                # Tenta baixar o bloco de um vizinho
                if self.download_block(block_to_get, (neighbor_host, neighbor_port)):
                    block_acquired = True

                    # Tornando-se um Seeder
                    # Ao receber o bloco, ele é adicionado a 'owned_blocks'
                    # e o 'run_server' automaticamente começará a servi-lo.
                    break # Conseguiu o bloco, passa para o próximo

            if not block_acquired:
                # Se não conseguiu de nenhum vizinho, espera um pouco e tenta de novo
                time.sleep(0.1)

        print(f"\n[Peer {self.port} Cliente]: DOWNLOAD COMPLETO! Arquivo remontado.\n")
        self.running = False # Pode parar o peer

    def download_block(self, block_index: int, neighbor_addr: tuple) -> bool:
        """Tenta baixar um único bloco de um vizinho específico."""
        try:
            # Conecta-se ao vizinho
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0) # Timeout curto
            s.connect(neighbor_addr)

            # Envia a solicitação (Protocolo)
            request = f"GET {block_index}\n"
            s.sendall(request.encode())

            # Recebe os dados do bloco
            block_data = b''
            while True:
                # Lê em chunks até o tamanho do bloco
                chunk = s.recv(BLOCK_SIZE)
                if not chunk:
                    break # Conexão fechada pelo servidor
                block_data += chunk

            s.close()

            # Validação simples do bloco (poderia ser por hash)
            if 0 < len(block_data) <= BLOCK_SIZE:
                # Escreve o bloco no arquivo local
                self._write_block(block_index, block_data)

                # Atualiza o registro de blocos local
                with self.lock:
                    self.owned_blocks.add(block_index)

                print(f"[Peer {self.port}]: Baixou Bloco {block_index} de {neighbor_addr[1]}. "
                      f"Progresso: {len(self.owned_blocks)}/{self.total_blocks} blocos.")
                return True

        except (socket.timeout, ConnectionRefusedError, ConnectionAbortedError):
            # print(f"[Peer {self.port}]: Falha ao conectar em {neighbor_addr[1]} para o bloco {block_index}")
            pass # Apenas tenta o próximo vizinho
        except Exception as e:
            print(f"[Peer {self.port}]: Erro ao baixar bloco {block_index}: {e}")

        return False

    def _read_block(self, block_index: int) -> bytes:
        """Lê um bloco específico do arquivo no disco."""
        offset = block_index * BLOCK_SIZE
        with self.lock: # Garante que não haja leitura/escrita conflitante
            with open(self.file_path, 'rb') as f:
                f.seek(offset)
                return f.read(BLOCK_SIZE)

    def _write_block(self, block_index: int, data: bytes):
        """Escreve um bloco específico no arquivo no disco."""
        offset = block_index * BLOCK_SIZE
        with self.lock: # Garante que não haja leitura/escrita conflitante
            with open(self.file_path, 'r+b') as f:
                f.seek(offset)
                f.write(data)

def create_dummy_file(filename: str, size_kb: int):
    "Cria um arquivo de teste com conteúdo aleatório."
    print(f"Criando arquivo de teste '{filename}' com {size_kb} KB...")
    with open(filename, 'wb') as f:
        f.write(os.urandom(size_kb * 1024))

def create_empty_file_for_leecher(filename: str, total_size: int):
    """Cria um arquivo vazio do tamanho correto para o Leecher."""
    print(f"Criando arquivo 'stub' para leecher '{filename}' com {total_size} bytes.")
    with open(filename, 'wb') as f:
        # Garante que o arquivo tenha o tamanho correto para a remontagem
        f.truncate(total_size)

def get_file_metadata(filename: str) -> dict:
    """Calcula metadados essenciais (Hash, Tamanho, Blocos)."""
    file_size = os.path.getsize(filename)
    total_blocks = math.ceil(file_size / BLOCK_SIZE)

    # Calcula o hash SHA-256 do arquivo original
    sha256 = hashlib.sha256()
    with open(filename, 'rb') as f:
        while chunk := f.read(BLOCK_SIZE):
            sha256.update(chunk)

    return {
        "hash": sha256.hexdigest(),
        "file_size": file_size,
        "total_blocks": total_blocks
    }

def verify_download(filename: str, original_hash: str) -> bool:
    "Verifica a integridade do arquivo baixado."
    print(f"Verificando integridade de '{filename}'...")
    if not os.path.exists(filename):
        print("  ERRO: Arquivo não encontrado.")
        return False

    metadata = get_file_metadata(filename)

    if metadata["hash"] == original_hash:
        print(f"  SUCESSO: Hash SHA-256 corresponde! (Tamanho: {metadata['file_size']} bytes)")
        return True
    else:
        print(f"  FALHA: Hash não corresponde.")
        print(f"    Esperado: {original_hash}")
        print(f"    Recebido: {metadata['hash']}")
        return False

if __name__ == "__main__":

    TEST_FILE_NAME = "file_B_original.txt"
    TEST_FILE_SIZE_KB = 1024 # 1 MB

    # Limpa arquivos de testes anteriores
    if os.path.exists("test_env"):
        shutil.rmtree("test_env")
    os.makedirs("test_env", exist_ok=True)

    ORIGINAL_FILE_PATH = os.path.join("test_env", TEST_FILE_NAME)

    # Cria o arquivo original
    create_dummy_file(ORIGINAL_FILE_PATH, TEST_FILE_SIZE_KB)

    # Gera os metadados
    metadata = get_file_metadata(ORIGINAL_FILE_PATH)

    print("\n--- Metadados do Arquivo Original ---")
    print(f"  Arquivo: {TEST_FILE_NAME}")
    print(f"  Tamanho: {metadata['file_size']} bytes")
    print(f"  Blocos:  {metadata['total_blocks']} (de {BLOCK_SIZE} bytes)")
    print(f"  Hash:    {metadata['hash']}")
    print("-" * 37 + "\n")

    # Configuração de vizinhos Estática
    # Peer 5001 conhece 5000 e 5002
    # Peer 5002 conhece 5000 e 5001
    # Peer 5000 (Seeder) conhece ambos

    PEER_CONFIGS = [
        {'port': 5001, 'neighbors': [(HOST, 5000), (HOST, 5002)], 'is_seeder': False},
        {'port': 5002, 'neighbors': [(HOST, 5000), (HOST, 5001)], 'is_seeder': False},
        {'port': 5000, 'neighbors': [(HOST, 5001), (HOST, 5002)], 'is_seeder': True},
    ]

    peers = []

    # Prepara arquivos e inicia os Peers
    for config in PEER_CONFIGS:
        port = config['port']
        peer_file_path = os.path.join("test_env", f"file_B_peer_{port}.txt")

        if config['is_seeder']:
            # O Seeder usa uma cópia do arquivo original
            shutil.copy(ORIGINAL_FILE_PATH, peer_file_path)
        else:
            # Leechers criam um arquivo vazio do tamanho correto
            create_empty_file_for_leecher(peer_file_path, metadata['file_size'])

        peer = Peer(
            port=port,
            neighbors=config['neighbors'],
            file_path=peer_file_path,
            file_hash=metadata['hash'],
            total_blocks=metadata['total_blocks'],
            is_seeder=config['is_seeder']
        )
        peers.append(peer)
        peer.start() # Inicia o peer (servidor e cliente)

    print("\n--- Simulação P2P Iniciada (1 Seeder, 2 Leechers) ---")
    print("Aguardando leechers completarem o download...\n")

    # Aguarda os peers não-seeder terminarem
    try:
        while True:
            time.sleep(2)
            all_done = True
            for p in peers:
                if not p.is_seeder and p.running:
                    all_done = False
                    break
            if all_done:
                print("\n--- Simulação Concluída ---")
                break
    except KeyboardInterrupt:
        print("\nSimulação interrompida.")
        for p in peers:
            p.running = False

    print("\n--- Verificação Final dos Arquivos ---")
    for p in peers:
        if not p.is_seeder:
            verify_download(p.file_path, metadata['hash'])

    print("\nLimpando ambiente de teste...")
    print("Feito.")