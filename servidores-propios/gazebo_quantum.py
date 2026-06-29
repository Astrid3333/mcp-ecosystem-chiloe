#!/usr/bin/env python3
"""
Gazebo Quantum MCP Server
Simulación de qutrits (sistemas cuánticos de 3 niveles) vía PennyLane,
con traducción de la medición a comandos ternarios para Gazebo Sim.

Puente conceptual con TritOS: en TritOS un trit físico {-1, 0, +1} se lee
desde un decodificador LM393 sobre coigüe grabado con LIG. Aquí, el trit
se origina en cambio de un circuito cuántico simulado de 3 niveles (qutrit),
cuyo colapso de medición {0, 1, 2} se remapea a {-1, 0, +1} antes de
enviarse como comando a un modelo en Gazebo.

Requiere en la máquina destino:
    pip install pennylane --break-system-packages
    pip install fastmcp --break-system-packages

Gazebo nunca "sabe" que hubo cómputo cuántico de por medio: este módulo
simula el qutrit en proceso separado y usa el resultado de la medición
como entrada discreta de control para gz_set_pose / gz_apply_force.
"""
import subprocess
import os
import math
import json
from typing import Optional

import numpy as np
import pennylane as qml

from fastmcp import FastMCP

mcp = FastMCP("gazebo-quantum")


# ----------------------------------------------------------------------
# Utilidades Gazebo (mismo patrón que gazebo_core.py / gazebo_entities.py,
# repetido aquí para que este servidor sea independiente y no dependa de
# imports cruzados entre los tres archivos fuente).
# ----------------------------------------------------------------------

def run_gz(args: list, timeout: int = 10) -> dict:
    """Ejecuta un comando gz y retorna resultado"""
    try:
        result = subprocess.run(
            ["gz"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "ok": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout después de {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> dict:
    cr = math.cos(roll / 2); sr = math.sin(roll / 2)
    cp = math.cos(pitch / 2); sp = math.sin(pitch / 2)
    cy = math.cos(yaw / 2);  sy = math.sin(yaw / 2)
    return {
        "x": sr * cp * cy - cr * sp * sy,
        "y": cr * sp * cy + sr * cp * sy,
        "z": cr * cp * sy - sr * sp * cy,
        "w": cr * cp * cy + sr * sp * sy,
    }


# ----------------------------------------------------------------------
# Capa cuántica: qutrit de 3 niveles (default.qutrit de PennyLane)
# ----------------------------------------------------------------------

def _build_qutrit_circuit(n_trits: int, gate: str, theta: float, seed: Optional[int]):
    """
    Construye y devuelve un QNode que prepara n_trits qutrits independientes,
    les aplica una puerta paramétrica de un solo qutrit, y mide en la base
    computacional {0, 1, 2}.

    gate: "TRX01" | "TRX02" | "TRY01" | "TRY02" | "THadamard" | "TShift"
    theta: ángulo de rotación en radianes (ignorado para THadamard/TShift)
    """
    dev = qml.device("default.qutrit", wires=n_trits, shots=1)
    if seed is not None:
        np.random.seed(seed)

    @qml.qnode(dev)
    def circuit():
        for w in range(n_trits):
            if gate == "TRX01":
                qml.TRX(theta, wires=w, subspace=[0, 1])
            elif gate == "TRX02":
                qml.TRX(theta, wires=w, subspace=[0, 2])
            elif gate == "TRY01":
                qml.TRY(theta, wires=w, subspace=[0, 1])
            elif gate == "TRY02":
                qml.TRY(theta, wires=w, subspace=[0, 2])
            elif gate == "THadamard":
                qml.THadamard(wires=w)
            elif gate == "TShift":
                qml.TShift(wires=w)
            else:
                raise ValueError(f"Puerta no soportada: {gate}")
        return [qml.sample(qml.GellMann(w, index=3)) for w in range(n_trits)]

    return circuit


def _gellmann3_to_basis_state(sample_value: float) -> int:
    """
    GellMann index=3 (análogo a Pauli-Z) tiene autovalores {+1, -1, 0}
    para los estados base {|0>, |1>, |2>} respectivamente, en la
    convención de PennyLane. Mapeamos el valor medido al estado base 0/1/2.
    """
    if sample_value > 0.5:
        return 0
    elif sample_value < -0.5:
        return 1
    else:
        return 2


def _basis_state_to_trit(basis_state: int) -> int:
    """Remapea el resultado de medición {0, 1, 2} a un trit clásico {-1, 0, +1}."""
    return {0: -1, 1: 0, 2: 1}[basis_state]


@mcp.tool()
def qtrit_sample(n_trits: int = 1, gate: str = "THadamard",
                  theta: float = 1.5708, seed: int = -1) -> str:
    """
    Simula n_trits qutrits independientes con PennyLane (default.qutrit),
    aplica una puerta de un solo qutrit a cada uno, mide en base computacional,
    y retorna tanto el estado base {0,1,2} como su trit equivalente {-1,0,+1}.

    gate: "THadamard" (superposición uniforme, default), "TShift" (cíclico
          determinista |i> -> |i+1 mod 3>), "TRX01"/"TRX02"/"TRY01"/"TRY02"
          (rotaciones parciales parametrizadas por theta en el subespacio indicado)
    theta: ángulo en radianes, usado solo por las puertas TRX*/TRY* (default pi/2)
    seed: semilla para reproducibilidad; -1 usa aleatoriedad del sistema

    Ejemplo de uso típico: gate="THadamard" da ~1/3 de probabilidad a cada
    uno de los 3 estados, análogo a un trit "justo" de TritOS pero generado
    por colapso cuántico en lugar de lectura física LIG/RP2040.
    """
    seed_val = None if seed == -1 else seed
    try:
        circuit = _build_qutrit_circuit(n_trits, gate, theta, seed_val)
        raw = circuit()
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

    raw = np.atleast_1d(np.array(raw)).flatten()
    basis_states = [_gellmann3_to_basis_state(float(v)) for v in raw]
    trits = [_basis_state_to_trit(b) for b in basis_states]

    return json.dumps({
        "ok": True,
        "gate": gate,
        "theta": theta,
        "n_trits": n_trits,
        "gellmann_raw": [float(v) for v in raw],
        "basis_states": basis_states,
        "trits": trits
    }, ensure_ascii=False)


# ----------------------------------------------------------------------
# Puente cuántico -> Gazebo
# ----------------------------------------------------------------------

@mcp.tool()
def qtrit_to_pose(model_name: str, gate: str = "THadamard", theta: float = 1.5708,
                   step: float = 0.5, seed: int = -1) -> str:
    """
    Mide UN qutrit y usa el trit resultante {-1, 0, +1} para mover un modelo
    existente en Gazebo a lo largo del eje X, en pasos discretos de tamaño 'step'.

    trit = -1  -> mueve -step en X
    trit =  0  -> no mueve (mantiene posición actual; reenvía pose con dx=0)
    trit = +1  -> mueve +step en X

    Esto es la unidad mínima de control: un colapso cuántico = un movimiento
    discreto de un actuador clásico en simulación.
    """
    seed_val = None if seed == -1 else seed
    try:
        circuit = _build_qutrit_circuit(1, gate, theta, seed_val)
        raw = float(np.atleast_1d(np.array(circuit())).flatten()[0])
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

    basis_state = _gellmann3_to_basis_state(raw)
    trit = _basis_state_to_trit(basis_state)
    dx = trit * step

    # Lee la pose actual para mover relativo (best-effort; si falla, asume origen)
    pose_r = run_gz(["model", "-m", model_name, "--pose"])
    x0, y0, z0 = 0.0, 0.0, 0.5
    if pose_r.get("ok") and pose_r.get("stdout"):
        try:
            parts = pose_r["stdout"].split()
            nums = [float(p) for p in parts if p.replace('.', '', 1).replace('-', '', 1).isdigit()]
            if len(nums) >= 3:
                x0, y0, z0 = nums[0], nums[1], nums[2]
        except Exception:
            pass

    new_x = x0 + dx
    req = (
        f'entity: {{name: "{model_name}" type: MODEL}} '
        f'pose: {{position: {{x: {new_x} y: {y0} z: {z0}}} '
        f'orientation: {{x: 0 y: 0 z: 0 w: 1}}}}'
    )
    r = run_gz(["service", "-s", "/world/default/set_pose",
                "--reqtype", "gz.msgs.Pose",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", req])

    return json.dumps({
        "ok": r.get("ok", False),
        "trit": trit,
        "basis_state": basis_state,
        "dx_applied": dx,
        "new_x": new_x,
        "gz_response": r.get("stdout") or r.get("stderr") or r.get("error", "")
    }, ensure_ascii=False)


@mcp.tool()
def qtrit_sequence_to_force(model_name: str, n_steps: int = 5, link_name: str = "link",
                             force_magnitude: float = 10.0, duration_ms: int = 500,
                             gate: str = "THadamard", theta: float = 1.5708,
                             seed: int = -1) -> str:
    """
    Genera una secuencia de n_steps trits (uno por medición de qutrit
    independiente) y aplica una fuerza en el eje X a un link de un modelo
    en Gazebo para cada trit:

    trit = -1 -> fuerza -force_magnitude en X
    trit =  0 -> sin fuerza (se omite el paso)
    trit = +1 -> fuerza +force_magnitude en X

    Cada paso se aplica secuencialmente con la duration_ms dada.
    Retorna la secuencia completa de trits generada y el resultado de
    cada llamada a Gazebo, útil para comparar contra una secuencia
    generada por TritOS real (hardware LIG/RP2040) en el mismo formato.
    """
    seed_val = None if seed == -1 else seed
    try:
        circuit = _build_qutrit_circuit(n_steps, gate, theta, seed_val)
        raw = np.atleast_1d(np.array(circuit())).flatten()
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

    basis_states = [_gellmann3_to_basis_state(float(v)) for v in raw]
    trits = [_basis_state_to_trit(b) for b in basis_states]

    results = []
    for trit in trits:
        if trit == 0:
            results.append({"trit": 0, "action": "skip", "gz_response": ""})
            continue
        fx = trit * force_magnitude
        req = (f'body_name: "{model_name}/{link_name}" '
               f'wrench: {{force: {{x: {fx} y: 0 z: 0}} torque: {{x: 0 y: 0 z: 0}}}} '
               f'duration: {{sec: 0 nsec: {duration_ms * 1000000}}}')
        r = run_gz(["service", "-s", "/world/default/wrench",
                    "--reqtype", "gz.msgs.EntityWrench",
                    "--reptype", "gz.msgs.Boolean",
                    "--timeout", "2000",
                    "--req", req])
        results.append({
            "trit": trit,
            "action": "force",
            "fx": fx,
            "gz_response": r.get("stdout") or r.get("stderr") or r.get("error", "")
        })

    return json.dumps({
        "ok": True,
        "trit_sequence": trits,
        "basis_states": basis_states,
        "steps": results
    }, ensure_ascii=False)


@mcp.tool()
def qtrit_circuit_info() -> str:
    """
    Retorna información sobre las puertas y convenciones soportadas en
    este módulo, útil como referencia rápida sin tener que leer el código.
    """
    info = {
        "device": "default.qutrit (PennyLane, simulador de estado puro)",
        "puertas_soportadas": {
            "THadamard": "Superposición uniforme entre |0>, |1>, |2> (~33% cada uno)",
            "TShift": "Shift cíclico determinista |i> -> |i+1 mod 3>, sin aleatoriedad",
            "TRX01": "Rotación X en el subespacio {|0>,|1>}, parametrizada por theta",
            "TRX02": "Rotación X en el subespacio {|0>,|2>}, parametrizada por theta",
            "TRY01": "Rotación Y en el subespacio {|0>,|1>}, parametrizada por theta",
            "TRY02": "Rotación Y en el subespacio {|0>,|2>}, parametrizada por theta",
        },
        "mapeo_basis_state_a_trit": {"0": -1, "1": 0, "2": 1},
        "observable_de_medicion": "GellMann index=3 (análogo de Pauli-Z para qutrits)",
        "nota": (
            "Este es cómputo cuántico SIMULADO clásicamente. No hay hardware "
            "cuántico real involucrado. El puente con TritOS es conceptual: "
            "ambos sistemas producen un trit {-1,0,+1}, pero TritOS lo lee de "
            "voltaje físico vía LM393 sobre coigüe-LIG, mientras que aquí se "
            "obtiene del colapso de medición de un qutrit simulado."
        )
    }
    return json.dumps(info, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
