#!/usr/bin/env python3
"""
verificador_padron.py

Cruza un padron electoral (o una lista de firmas de una peticion) contra una
lista de referencia -por ejemplo, registros de defuncion o un listado de
personas registradas como residentes en el extranjero- para SENALAR posibles
coincidencias que ameriten revision manual.

QUE HACE Y QUE NO HACE
-----------------------
- Genera una lista de candidatos a revisar (CSV). No borra, invalida ni
  certifica nada por si mismo.
- Requiere coincidencia de nombre (fuzzy) + fecha de nacimiento, o un
  identificador unico exacto (ej. ultimos 4 digitos de SSN), para reducir
  falsos positivos. El emparejamiento por nombre solo es notoriamente
  propenso a error (homonimos, transliteraciones, errores de tipeo).

CONTEXTO LEGAL A TENER EN CUENTA (EE.UU.)
-------------------------------------------
- La National Voter Registration Act (NVRA) y las leyes estatales regulan
  como y cuando se puede remover a alguien del padron; en general exigen
  notificacion previa y un proceso, no una baja automatica por un cruce de
  datos.
- El acceso a padrones electorales y a registros de defuncion varia por
  estado: muchos requieren una solicitud formal de registros publicos y
  tienen restricciones sobre el uso que se le puede dar a esos datos.
- Historicamente, programas de cruce de datos a gran escala (ej. Crosscheck)
  han producido muchos falsos positivos por depender solo del nombre y la
  fecha de nacimiento. Trata cualquier "coincidencia" como punto de partida
  para verificar, no como conclusion.

USO
---
python3 verificador_padron.py padron.csv referencia.csv \
    --col-nombre nombre --col-fecha fecha_nacimiento --col-id id_unico \
    --umbral 90 --salida coincidencias.csv

Ambos CSV deben tener encabezados. Como minimo necesitan una columna de
nombre y una de fecha de nacimiento (los nombres de columna son
configurables via argumentos).
"""

import argparse
import csv
import sys
import unicodedata
from datetime import datetime

try:
    from rapidfuzz import fuzz
except ImportError:
    print("Falta la dependencia rapidfuzz. Instala con:\n"
          "  pip install rapidfuzz --break-system-packages", file=sys.stderr)
    sys.exit(1)


def normalizar(texto):
    if not texto:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(texto.split())


def normalizar_fecha(fecha_str):
    """Intenta parsear varios formatos de fecha comunes y normalizar a YYYY-MM-DD."""
    formatos = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(str(fecha_str).strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return normalizar(fecha_str)


def cargar_csv(ruta, col_nombre, col_fecha, col_id=None):
    registros = []
    with open(ruta, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if col_nombre not in reader.fieldnames or col_fecha not in reader.fieldnames:
            print(f"Aviso: {ruta} no tiene las columnas '{col_nombre}' / '{col_fecha}'. "
                  f"Columnas disponibles: {reader.fieldnames}", file=sys.stderr)
        for fila in reader:
            registros.append({
                "raw": fila,
                "nombre_norm": normalizar(fila.get(col_nombre, "")),
                "fecha_norm": normalizar_fecha(fila.get(col_fecha, "")),
                "id": normalizar(fila.get(col_id, "")) if col_id else None,
            })
    return registros


def cruzar(padron, referencia, umbral_nombre=90):
    coincidencias = []
    # Indexar la referencia por fecha de nacimiento para no comparar todos
    # contra todos (O(n*m) -> mucho mas rapido en listas grandes).
    indice = {}
    for r in referencia:
        indice.setdefault(r["fecha_norm"], []).append(r)

    for elector in padron:
        candidatos = indice.get(elector["fecha_norm"], [])
        for cand in candidatos:
            score = fuzz.token_sort_ratio(elector["nombre_norm"], cand["nombre_norm"])
            id_coincide = bool(
                elector["id"] and cand["id"] and elector["id"] == cand["id"]
            )
            if score >= umbral_nombre or id_coincide:
                coincidencias.append({
                    "elector": elector["raw"],
                    "referencia": cand["raw"],
                    "score_nombre": round(score, 1),
                    "id_coincide": id_coincide,
                })
    # Los casos con id_coincide=True o score mas alto primero
    coincidencias.sort(key=lambda c: (c["id_coincide"], c["score_nombre"]), reverse=True)
    return coincidencias


def main():
    ap = argparse.ArgumentParser(
        description="Cruza un padron electoral contra una lista de referencia "
                     "(defunciones, residentes en el extranjero, etc.) y genera "
                     "candidatos para revision manual.")
    ap.add_argument("padron_csv", help="CSV del padron electoral o de firmas")
    ap.add_argument("referencia_csv", help="CSV de referencia (defunciones, etc.)")
    ap.add_argument("--col-nombre", default="nombre")
    ap.add_argument("--col-fecha", default="fecha_nacimiento")
    ap.add_argument("--col-id", default=None,
                     help="Columna de identificador unico opcional (ej. ultimos 4 digitos de SSN)")
    ap.add_argument("--umbral", type=int, default=90, help="Umbral de similitud de nombre (0-100)")
    ap.add_argument("--salida", default="coincidencias.csv")
    args = ap.parse_args()

    padron = cargar_csv(args.padron_csv, args.col_nombre, args.col_fecha, args.col_id)
    referencia = cargar_csv(args.referencia_csv, args.col_nombre, args.col_fecha, args.col_id)

    coincidencias = cruzar(padron, referencia, args.umbral)

    if not coincidencias:
        print("No se encontraron coincidencias con los criterios dados.")
        return

    with open(args.salida, "w", newline="", encoding="utf-8") as f:
        writer = None
        for c in coincidencias:
            fila = {f"padron_{k}": v for k, v in c["elector"].items()}
            fila.update({f"referencia_{k}": v for k, v in c["referencia"].items()})
            fila["score_nombre"] = c["score_nombre"]
            fila["id_coincide"] = c["id_coincide"]
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(fila.keys()))
                writer.writeheader()
            writer.writerow(fila)

    print(f"{len(coincidencias)} posibles coincidencias escritas en {args.salida}")
    print("Recuerda: esto es un punto de partida para revision manual, no una conclusion definitiva.")


if __name__ == "__main__":
    main()
