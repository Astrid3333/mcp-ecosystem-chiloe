"""
parsers.py
Extraccion basica de resultados desde logs de GROMACS (mdrun) y LAMMPS.

Son parsers heuristicos pensados para dar un resumen rapido dentro de una
respuesta MCP, no para reemplazar 'gmx energy' o un analisis completo.
"""

import re
from pathlib import Path


# Nombres que GROMACS usa para el log completo que escribe en el directorio
# de trabajo. El stdout capturado por el job solo trae la salida de pantalla.
GROMACS_LOG_NAMES = ("topol.log", "md.log", "mdout.log")


def parse_gromacs_log(log_path: str, cwd: str | None = None) -> dict:
    """
    Parsea el log de GROMACS.

    Si se pasa 'cwd', se busca primero el log completo que GROMACS escribe en el
    directorio de trabajo (topol.log / md.log), que es el unico que contiene los
    bloques de energia y el 'Finished mdrun'. Si no existe, se usa 'log_path'
    (el stdout capturado del proceso).
    """
    p = Path(log_path)
    source = p
    if cwd:
        for name in GROMACS_LOG_NAMES:
            candidate = Path(cwd) / name
            if candidate.exists() and candidate.stat().st_size > 0:
                source = candidate
                break

    if not source.exists():
        return {"error": f"No existe el log: {log_path}"}

    text = source.read_text(errors="ignore")

    # Bloques "Energies (kJ/mol)" que GROMACS imprime periodicamente
    blocks = []
    for m in re.finditer(r"Energies \(kJ/mol\)\n(.*?)\n\n", text, re.S):
        blocks.append(m.group(1).strip())

    finished = "Finished mdrun" in text or "Finished mdrun on rank" in text
    # Solo marcadores de error real: el texto normal de GROMACS menciona
    # "the error in the average pressure", asi que buscar 'error' a secas
    # daba falsos positivos en cualquier simulacion exitosa.
    had_error = bool(
        re.search(r"Fatal error|^ERROR \d+|\bSegmentation fault\b", text, re.M)
    )

    performance = None
    perf_match = re.search(r"Performance:\s+([\d.]+)\s+ns/day", text)
    if perf_match:
        performance = f"{perf_match.group(1)} ns/day"
    else:
        # GROMACS 2018+ imprime las unidades en la linea anterior:
        #   (ns/day)    (hour/ns)
        #   Performance:       88.701        0.271
        perf_match = re.search(r"Performance:\s+([\d.]+)", text)
        if perf_match:
            performance = f"{perf_match.group(1)} ns/day"

    return {
        "finished": finished,
        "had_error_keyword": had_error,
        "energy_blocks_found": len(blocks),
        "last_energy_block": blocks[-1] if blocks else None,
        "performance": performance,
        "log_file": str(source),
    }


def parse_lammps_log(log_path: str) -> dict:
    p = Path(log_path)
    if not p.exists():
        return {"error": f"No existe el log: {log_path}"}

    text = p.read_text(errors="ignore")

    # Tabla de thermo: empieza en una linea que arranca con "Step" y termina en "Loop time"
    rows = []
    header = None
    for match in re.finditer(r"^Step.*$", text, re.M):
        start = match.start()
        end = text.find("Loop time", start)
        if end == -1:
            end = len(text)
        chunk = text[start:end].strip().splitlines()
        if chunk:
            header = chunk[0].split()
            for line in chunk[1:]:
                parts = line.split()
                if len(parts) == len(header):
                    rows.append(dict(zip(header, parts)))

    finished = "Total wall time" in text
    had_error = bool(re.search(r"ERROR", text))

    return {
        "finished": finished,
        "had_error_keyword": had_error,
        "thermo_header": header,
        "n_thermo_rows": len(rows),
        "last_thermo_row": rows[-1] if rows else None,
        "first_thermo_row": rows[0] if rows else None,
    }
