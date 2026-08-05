FROM python:3.9-slim

# Instalar dependencias del sistema necesarias si las hubiera
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements y hacer la instalación
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto por defecto de Streamlit
EXPOSE 7860

# Comando para ejecutar Streamlit en el puerto de HF Spaces (7860)
CMD ["streamlit", "run", "app.py", "--server.port", "7860", "--server.address", "0.0.0.0"]
