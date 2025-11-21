# Script de diagnóstico
from pypdf import PdfReader
reader = PdfReader("R579 - DESPACHO 25073IC04091365E.pdf")
texto = reader.pages[99].extract_text() # O la página donde esté Cond. Venta
print(repr(texto[:1000])) # Imprime los caracteres exactos con \n, \t, etc.
texto = reader.pages[100].extract_text() # O la página donde esté Cond. Venta
print(repr(texto[:1000]))