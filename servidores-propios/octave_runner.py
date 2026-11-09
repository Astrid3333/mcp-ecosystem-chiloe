"""Ejecutor de GNU Octave compartido por el servidor MCP y sus modulos tool.

Vive en un modulo propio para que los modulos tool puedan obtener `run_octave`
sin importar el modulo `server` (que dentro del servidor es el propio
`octave_mcp.py` registrado en `sys.modules`). Evita ademas el acoplamiento
del shim `sys.modules["server"]`, que resolvia el import de forma implicita.
"""

from __future__ import annotations

import shutil
import subprocess


def _octave_bin() -> str:
    """Devuelve la ruta absoluta al binario de octave (evita B607 ruta parcial)."""
    path = shutil.which("octave")
    if not path:
        raise RuntimeError("octave no encontrado en PATH")
    return path


def run_octave(code: str, timeout: int = 30) -> str:
    """Ejecuta codigo GNU Octave y devuelve stdout+stderr combinados."""
    result = subprocess.run(
        [_octave_bin(), "--no-gui", "--eval", code],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout + result.stderr
