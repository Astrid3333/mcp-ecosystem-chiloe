"""
gazebo_utils.py
Utilidades compartidas entre los conectores MCP de Gazebo (gazebo_core,
gazebo_entities, gazebo_quantum). Centraliza run_gz y euler_to_quaternion
para evitar triplicación de código y asegurar que una corrección se aplique
a los tres servidores a la vez.
"""
import subprocess
import math


def run_gz(args: list, timeout: int = 10) -> dict:
    """Ejecuta un comando gz y retorna resultado."""
    try:
        result = subprocess.run(
            ["gz"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout después de {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> dict:
    """
    Convierte ángulos de Euler (radianes) a cuaternión (x, y, z, w).
    Convención ZYX (yaw, pitch, roll).
    """
    cr = math.cos(roll / 2); sr = math.sin(roll / 2)
    cp = math.cos(pitch / 2); sp = math.sin(pitch / 2)
    cy = math.cos(yaw / 2);  sy = math.sin(yaw / 2)
    return {
        "x": sr * cp * cy - cr * sp * sy,
        "y": cr * sp * cy + sr * cp * sy,
        "z": cr * cp * sy - sr * sp * cy,
        "w": cr * cp * cy + sr * sp * sy,
    }
