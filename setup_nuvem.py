import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Esquema alinhado com o que services/banco.py, services/analista.py e app.py usam.
# Todos os comandos são idempotentes (IF NOT EXISTS), então o script também serve
# para atualizar um banco criado por versões antigas.
SCHEMA = [
    # Clientes (empresas). A relação com os números de WhatsApp fica em numeros_autorizados.
    """
    CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        whatsapp VARCHAR(50) UNIQUE,
        planilha_id VARCHAR(100) NOT NULL,
        cnpj VARCHAR(20),
        contexto_ia TEXT DEFAULT ''
    )
    """,
    # Números que podem falar com o bot em nome de cada cliente
    """
    CREATE TABLE IF NOT EXISTS numeros_autorizados (
        id SERIAL PRIMARY KEY,
        telefone VARCHAR(50) UNIQUE NOT NULL,
        client_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE
    )
    """,
    # Estoque atual por produto
    """
    CREATE TABLE IF NOT EXISTS estoque (
        id SERIAL PRIMARY KEY,
        client_id INTEGER REFERENCES clientes(id),
        product_id VARCHAR(100) NOT NULL,
        nome TEXT,
        especificacao TEXT,
        quantity NUMERIC DEFAULT 0,
        peso NUMERIC DEFAULT 0,
        estoque_minimo NUMERIC DEFAULT 0,
        custo_unitario NUMERIC DEFAULT 0,
        preco_venda NUMERIC DEFAULT 0,
        ultima_atualizacao TIMESTAMP
    )
    """,
    # Histórico de movimentações (ENTRADA, SAIDA, ESTORNO)
    """
    CREATE TABLE IF NOT EXISTS historico (
        id SERIAL PRIMARY KEY,
        client_id INTEGER REFERENCES clientes(id),
        product_id VARCHAR(100) NOT NULL,
        quantidade NUMERIC,
        tipo VARCHAR(50),
        data TIMESTAMP,
        valor_total NUMERIC DEFAULT 0
    )
    """,
    # Migração de bancos criados por versões antigas do script
    "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cnpj VARCHAR(20)",
    "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS contexto_ia TEXT DEFAULT ''",
    "ALTER TABLE clientes ALTER COLUMN whatsapp DROP NOT NULL",
    "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS estoque_minimo NUMERIC DEFAULT 0",
    "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS custo_unitario NUMERIC DEFAULT 0",
    "ALTER TABLE estoque ADD COLUMN IF NOT EXISTS preco_venda NUMERIC DEFAULT 0",
    "ALTER TABLE historico ADD COLUMN IF NOT EXISTS valor_total NUMERIC DEFAULT 0",
]


def setup_supabase():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            port=os.getenv('DB_PORT', 5432)
        )
        cursor = conn.cursor()

        for comando in SCHEMA:
            cursor.execute(comando)

        conn.commit()
        cursor.close()
        conn.close()
        print("🚀 Banco de dados na nuvem (Supabase) criado/atualizado com sucesso!")

    except Exception as e:
        print(f"❌ Erro ao conectar ou criar tabelas: {e}")


if __name__ == "__main__":
    setup_supabase()
