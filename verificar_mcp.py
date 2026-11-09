#!/usr/bin/env python3
"""
verificar_mcp.py

Verifica que cada servidor MCP configurado en claude_desktop_config.json
responda correctamente al handshake JSON-RPC 'initialize'.

Uso:
    python3 verificar_mcp.py
    python3 verificar_mcp.py --timeout 8
    python3 verificar_mcp.py --solo github,octave
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

CONFIG_PATH = pathlib.Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
TEMPLATE_PATH = pathlib.Path(__file__).resolve().parent / "claude_desktop_config.template.json"

INIT_MSG: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "verificador-manual", "version": "1.0"},
    },
}


def test_server(
    name: str,
    cfg: Dict[str, Any],
    timeout: float,
) -> Tuple[str, str, Any, Optional[str]]:
    """Ejecuta el handshake JSON-RPC 'initialize' contra un servidor MCP.

    Args:
        name: Nombre del servidor (clave en mcpServers).
        cfg: Configuración del servidor (debe contener 'command' y opcional 'args', 'env').
        timeout: Tiempo máximo de espera en segundos.

    Returns:
        Tupla con (nombre, estado, detalle, stderr_opcional).
        Estados posibles: OK, RESPONDIO_CON_ERROR, SIN_RESPUESTA_JSONRPC, FALLO, TIMEOUT, ERROR.
    """
    command = cfg.get("command")
    args: List[str] = cfg.get("args", [])
    env_extra: Dict[str, str] = cfg.get("env", {})

    if not command:
        return name, "SIN_COMANDO", "No tiene 'command' definido en el config", None

    env = os.environ.copy()
    env.update(env_extra)

    payload = json.dumps(INIT_MSG) + "\n"

    try:
        proc = subprocess.run(
            [command, *args],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return name, "FALLO", f"Comando no encontrado: {command}", None
    except subprocess.TimeoutExpired:
        return name, "TIMEOUT", f"No respondió en {timeout}s (puede ser normal si el server espera más mensajes)", None
    except Exception as e:
        return name, "ERROR", str(e), None

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    # Buscar una línea de stdout que parsee como JSON-RPC válido con resultado
    respuesta_valida: Optional[Dict[str, Any]] = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                respuesta_valida = parsed
                break
        except json.JSONDecodeError:
            continue

    if respuesta_valida:
        if "error" in respuesta_valida:
            return name, "RESPONDIO_CON_ERROR", respuesta_valida["error"], stderr[:300]
        server_info = respuesta_valida.get("result", {}).get("serverInfo", {})
        return name, "OK", server_info, stderr[:300] if stderr else None
    else:
        detalle = stdout[:300] if stdout else "(stdout vacío)"
        return name, "SIN_RESPUESTA_JSONRPC", detalle, stderr[:300] if stderr else None


def _load_config(config_path: pathlib.Path) -> Dict[str, Any]:
    """Carga el archivo de configuración de Claude Desktop.

    Args:
        config_path: Ruta al archivo JSON de configuración.

    Returns:
        Diccionario con el contenido del config, o vacío si no existe.
    """
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> None:
    """Punto de entrada principal. Ejecuta el handshake contra todos los servidores MCP configurados."""
    parser = argparse.ArgumentParser(description="Verifica servidores MCP configurados")
    parser.add_argument("--timeout", type=float, default=6.0, help="Tiempo de espera en segundos (default: 6.0)")
    parser.add_argument(
        "--solo",
        type=str,
        default=None,
        help="Lista de nombres separados por coma, ej: github,octave",
    )
    args = parser.parse_args()

    config_path = CONFIG_PATH
    if not CONFIG_PATH.exists() and TEMPLATE_PATH.exists():
        print(
            f"Aviso: no existe el config real en {CONFIG_PATH}; "
            f"usando el template del repo ({TEMPLATE_PATH})"
        )
        config_path = TEMPLATE_PATH
    elif not CONFIG_PATH.exists():
        print(f"No se encontró el config en {CONFIG_PATH}")
        sys.exit(1)

    data = _load_config(config_path)
    servers: Dict[str, Any] = data.get("mcpServers", {})

    if args.solo:
        filtro = set(s.strip() for s in args.solo.split(","))
        servers = {k: v for k, v in servers.items() if k in filtro}

    if not servers:
        print("No hay servidores para probar.")
        sys.exit(0)

    print(f"Probando {len(servers)} servidor(es) MCP (timeout={args.timeout}s c/u)...\n")

    resultados: List[Tuple[str, str, Any, Optional[str]]] = []
    for name, cfg in servers.items():
        print(f"  -> {name} ...", end=" ", flush=True)
        res = test_server(name, cfg, args.timeout)
        resultados.append(res)
        print(res[1])

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    ok = [r for r in resultados if r[1] == "OK"]
    fallos = [r for r in resultados if r[1] != "OK"]

    for name, status, detalle, stderr in resultados:
        marca = "✓" if status == "OK" else "✗"
        print(f"{marca} {name:20s} {status}")
        if status != "OK":
            print(f"    detalle: {detalle}")
            if stderr:
                print(f"    stderr:  {stderr}")

    print("=" * 60)
    print(f"OK: {len(ok)}/{len(resultados)}  |  Con problemas: {len(fallos)}/{len(resultados)}")


if __name__ == "__main__":
    main()
