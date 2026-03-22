import sqlite3

def setup_profissional():
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()

    # Tabela de Clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            whatsapp TEXT UNIQUE NOT NULL,
            planilha_id TEXT NOT NULL
        )
    """)

    # Tabela de Estoque (com product_id)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            product_id TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            peso REAL DEFAULT 0,
            ultima_atualizacao DATETIME,
            FOREIGN KEY (client_id) REFERENCES clientes(id)
        )
    """)

    # Tabela de Histórico
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            product_id TEXT NOT NULL,
            quantidade REAL,
            tipo TEXT, -- 'ENTRADA' ou 'ESTORNO'
            data DATETIME,
            FOREIGN KEY (client_id) REFERENCES clientes(id)
        )
    """)

    conn.commit()
    conn.close()
    print("🏗️ Banco de Dados (Versão 2026 - product_id) estruturado com sucesso!")

if __name__ == "__main__":
    setup_profissional()