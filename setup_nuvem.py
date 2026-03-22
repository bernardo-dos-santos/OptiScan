import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

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

        # Tabela de Clientes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) NOT NULL,
                whatsapp VARCHAR(50) UNIQUE NOT NULL,
                planilha_id VARCHAR(100) NOT NULL
            )
        """)

        # Tabela de Estoque
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estoque (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clientes(id),
                product_id VARCHAR(100) NOT NULL,
                quantity NUMERIC DEFAULT 0,
                peso NUMERIC DEFAULT 0,
                ultima_atualizacao TIMESTAMP
            )
        """)

        # Tabela de Histórico
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clientes(id),
                product_id VARCHAR(100) NOT NULL,
                quantidade NUMERIC,
                tipo VARCHAR(50),
                data TIMESTAMP
            )
        """)

        # Insere um cliente padrão para o seu ID 1 não quebrar nos testes
        cursor.execute("""
            INSERT INTO clientes (nome, whatsapp, planilha_id) 
            VALUES ('Cliente Teste', 'seu_numero_ou_twilio', 'COLOQUE_O_ID_DA_PLANILHA_AQUI_PARA_TESTE')
            ON CONFLICT (whatsapp) DO NOTHING;
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("🚀 Banco de dados na nuvem (Supabase) criado com sucesso!")

    except Exception as e:
        print(f"❌ Erro ao conectar ou criar tabelas: {e}")

if __name__ == "__main__":
    setup_supabase()