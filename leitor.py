from PIL import Image
from pyzbar.pyzbar import decode as ler_codigo


conteudo_codigo = ler_codigo(Image.open("codigo.jpeg"))


if conteudo_codigo:

    texto_extraido = conteudo_codigo[0].data.decode('utf-8')
    

    print("O código lido foi:", texto_extraido)
else:
    print("Nenhum código encontrado na imagem.")