import os

# Evita que los tests escriban en la base de auditoría real definida en .env.
os.environ["DATABASE_URL"] = ""
