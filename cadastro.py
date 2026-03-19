import sqlite3

def cadastrar_produto(nome, codigo_barras, preco, quantidade):
    try:
        # 1. Conecta ao banco de dados estoque.db
        con = sqlite3.connect('estoque.db')
        cursor = con.cursor()
        
        # 2. Executa o comando SQL para inserir os dados na tabela [3]
        cursor.execute("""
            INSERT INTO estoque (item_name, hs_code, price, quantity) 
            VALUES (?, ?, ?, ?)
        """, (nome, codigo_barras, preco, quantidade))
        
        # 3. Confirma a gravação (commit) e fecha a conexão
        con.commit()
        con.close()
        
        print(f"Sucesso! Produto '{nome}' cadastrado com o código {codigo_barras}.")
        
    except Exception as e:
        print(f"Ocorreu um erro ao cadastrar: {e}")

# Testando a nossa função com o código de barras real que você extraiu na etapa anterior!
cadastrar_produto("Arroz Branco 1kg", "7891000343883", "5.99", "50")