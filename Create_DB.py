import sqlite3

def Create_DB():

    con = sqlite3.connect(database=r'estoque.db')
    cur = con.cursor()
    

    cur.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            hs_code TEXT, 
            price TEXT,
            quantity TEXT
        )
    """)
    
 
    con.commit()
    print("Banco de dados e tabela de estoque criados com sucesso!")


Create_DB()