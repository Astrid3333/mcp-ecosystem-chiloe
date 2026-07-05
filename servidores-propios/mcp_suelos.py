from mcp.server.fastmcp import FastMCP
import requests
import subprocess
import json

mcp = FastMCP("analisis-suelos")

@mcp.tool()
def analizar_suelo(lat: float, lon: float) -> str:
    """Analiza el suelo en coordenadas dadas"""
    r = requests.get(
        "https://rest.isric.org/soilgrids/v2.0/properties/query",
        params={
            "lon": lon, "lat": lat,
            "property": ["clay","sand","silt","phh2o"],
            "depth": ["0-5cm"],
            "value": "mean"
        }
    )
    suelo = r.json()
    s = requests.get(
        "https://earthquake.usgs.gov/fdsnws/event/1/query",
        params={
            "format": "geojson",
            "latitude": lat, "longitude": lon,
            "maxradiuskm": 100,
            "minmagnitude": 5.0,
            "limit": 5
        }
    )
    sismos = s.json()["features"]
    return json.dumps({
        "suelo": suelo,
        "sismos": [{"mag": x["properties"]["mag"],
                    "lugar": x["properties"]["place"]}
                   for x in sismos]
    })

@mcp.tool()
def ejecutar_octave(script: str) -> str:
    """Ejecuta un script de Octave y devuelve el resultado"""
    with open("/tmp/temp_script.m", "w") as f:
        f.write(script)
    result = subprocess.run(
        ["octave", "--norc", "/tmp/temp_script.m"],
        capture_output=True, text=True
    )
    return result.stdout

if __name__ == "__main__":
    mcp.run()
