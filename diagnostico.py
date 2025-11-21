# Script de diagnóstico
from pypdf import PdfReader
reader = PdfReader("D348 - Despacho 25062IC05000702L .pdf")
texto = reader.pages[26].extract_text() # O la página donde esté Cond. Venta
print(repr(texto[:1000])) # Imprime los caracteres exactos con \n, \t, etc.