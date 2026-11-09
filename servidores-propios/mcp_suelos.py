from mcp.server.fastmcp import FastMCP
import requests
import subprocess
import json
import tempfile
import os
import shutil

mcp = FastMCP("analisis-suelos")

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def _octave_bin():
    """Devuelve la ruta absoluta al binario de octave (evita B607 ruta parcial)."""
    path = shutil.which("octave")
    if not path:
        raise RuntimeError("octave no encontrado en PATH")
    return path


@mcp.tool()
def analizar_suelo(lat: float, lon: float) -> str:
    """Analiza el suelo en coordenadas dadas (ISRIC SoilGrids + sismos USGS cercanos)."""
    # --- Suelo (ISRIC SoilGrids) ---
    try:
        r = requests.get(
            SOILGRIDS_URL,
            params={
                "lon": lon, "lat": lat,
                "property": ["clay", "sand", "silt", "phh2o"],
                "depth": ["0-5cm"],
                "value": "mean",
            },
            timeout=15,
        )
        r.raise_for_status()
        suelo = r.json()
    except Exception as e:
        suelo = {"error": f"No se pudo consultar ISRIC SoilGrids: {e}"}

    # --- Sismos (USGS) ---
    try:
        s = requests.get(
            USGS_URL,
            params={
                "format": "geojson",
                "latitude": lat, "longitude": lon,
                "maxradiuskm": 100,
                "minmagnitude": 5.0,
                "limit": 5,
            },
            timeout=15,
        )
        s.raise_for_status()
        s_data = s.json()
        sismos_raw = s_data.get("features", [])
        sismos = [
            {
                "mag": x.get("properties", {}).get("mag"),
                "lugar": x.get("properties", {}).get("place"),
            }
            for x in sismos_raw
        ]
    except Exception as e:
        sismos = {"error": f"No se pudo consultar USGS: {e}"}

    return json.dumps({
        "suelo": suelo,
        "sismos": sismos,
    }, ensure_ascii=False)


@mcp.tool()
def ejecutar_octave(script: str, timeout_s: int = 30) -> str:
    """Ejecuta un script de Octave y devuelve el resultado (stdout, stderr y código de salida)."""
    fd, script_path = tempfile.mkstemp(suffix=".m", prefix="suelo_")
    with os.fdopen(fd, "w") as tf:
        tf.write(script)

    try:
        result = subprocess.run(
            [_octave_bin(), "--norc", script_path],
            capture_output=True, text=True, timeout=timeout_s,
        )
        return json.dumps({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": f"Octave excedió el timeout de {timeout_s}s",
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }, ensure_ascii=False)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


if __name__ == "__main__":
    mcp.run()
