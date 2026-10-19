import pandas as pd
from core.models import Escuela

archivo = "/home/admin/noc/sistema/core/INTERNET.xlsx"

df = pd.read_excel(archivo, header=0)
df.columns = df.columns.astype(str).str.strip()

print("Columnas detectadas:")
print(df.columns.tolist())

def convertir_float(valor):
    try:
        return float(valor)
    except:
        return None

def convertir_int(valor):
    try:
        if pd.isna(valor):
            return None
        return int(valor)
    except:
        return None

cont = 0
saltadas = 0

for _, fila in df.iterrows():
    lat = convertir_float(fila.get("LAT"))
    lon = convertir_float(fila.get("LONG"))

    # Si no tiene coordenadas, no es una escuela
    if lat is None or lon is None:
        saltadas += 1
        continue

    Escuela.objects.create(
        numero = convertir_int(fila.get("Nª")),
        predio_final = str(fila.get("PREDIO FINAL", "")).strip(),
        unificar = str(fila.get("UNIFICAR", "")).strip(),
        predio = str(fila.get("PREDIO", "")).strip(),
        cue = str(fila.get("cue", "")).strip(),
        escuelas = str(fila.get("escuelas", "")).strip(),
        localidad = str(fila.get("LOCALIDAD", "")).strip(),
        departamento = str(fila.get("DEPARTAMENTO", "")).strip(),
        nivel = str(fila.get("NIVEL", "")).strip(),
        internet= str(fila.get("INTERNET", "")).strip(),
        lat = lat,
        lon = lon,

    )
    cont += 1

print("Escuelas importadas:", cont)
print("Filas ignoradas:", saltadas)

