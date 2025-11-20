# Usar una imagen base ligera de Python para ahorrar espacio y memoria
FROM python:3.9-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar primero los requerimientos para aprovechar la caché de Docker
COPY requirements.txt .

# Instalar dependencias del sistema necesarias para algunas librerías de Python (opcional pero recomendado para pypdf/pandas)
# y las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código de la aplicación
COPY . .

# Exponer el puerto 8000. Azure App Service busca este puerto o el 80 por defecto.
EXPOSE 8000

# Comando de inicio:
# 1. streamlit run app.py: Ejecuta la app.
# 2. --server.port=8000: Fuerza a Streamlit a usar el puerto 8000 (Azure no usa el 8501 por defecto).
# 3. --server.address=0.0.0.0: Permite conexiones externas.
CMD sh -c "streamlit run app.py --server.port=8000 --server.address=0.0.0.0"