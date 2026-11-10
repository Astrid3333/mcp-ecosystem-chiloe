from mcp.server.fastmcp import FastMCP
import requests
import subprocess
import tempfile
import os

from octave_runner import octave_bin

mcp = FastMCP("analisis-suelos")

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


@mcp.tool()
def analizar_suelo(lat: float, lon: float) -> dict:
    """Analiza el suelo en coordenadas dadas (ISRIC SoilGrids + sismos USGS cercanos).

    Respuesta: dict con las claves 'suelo' (propiedades del SoilGrids en el punto) y 'sismos'
    (eventos USGS cercanos). Cada sub-dict trae su propia clave 'error' si esa consulta falló.
    """
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

    return {
        "suelo": suelo,
        "sismos": sismos,
    }


@mcp.tool()
def ejecutar_octave(script: str, timeout_s: int = 30) -> dict:
    """Ejecuta un script de Octave y devuelve el resultado.

    Respuesta: dict con las claves 'stdout' (salida del script), 'stderr' (salida de error),
    'returncode' (código de salida; 0 = ok) y, si el script excede el timeout, 'error' con el
    motivo y 'returncode' en None.

    Ojo con el contrato: desde la versión corregida la respuesta es un objeto JSON con esas
    claves, no el stdout crudo. Para el texto del script, leé la clave 'stdout'.
    """
    fd, script_path = tempfile.mkstemp(suffix=".m", prefix="suelo_")
    with os.fdopen(fd, "w") as tf:
        tf.write(script)

    try:
        result = subprocess.run(
            [octave_bin(), "--norc", script_path],
            capture_output=True, text=True, timeout=timeout_s,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "error": f"Octave excedió el timeout de {timeout_s}s",
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


if __name__ == "__main__":
    mcp.run()
