#!/usr/bin/env python3
"""
goertzel_tool.py - Tool MCP para el algoritmo de Goertzel con formulaciones K, alpha, beta e hibrida.

Implementa en Python las cuatro formulaciones numericas del algoritmo de Goertzel para
calcular un coeficiente DFT en una frecuencia angular w dada, con comparacion opcional
contra numpy.fft.

Formulaciones:
  - K      : 2*cos(w)           (zona media, cerca de pi/2)
  - alpha  : 4*sin^2(w/2)       (w pequeño, w < pi/4)
  - beta   : 4*cos^2(w/2)       (espejo para w > pi/2, cerca de pi)
  - hibrida: alpha si w < pi/2, beta si w >= pi/2

Referencia experimental (N = 131072, ruido gaussiano, error relativo vs long double):
  bin 1  (w=4.8e-05):  K=4.8e-08,  alpha=1.7e-13, beta=2.7e-07, hibrida=1.7e-13
  bin 1000 (w=4.8e-02): K=4.9e-12, alpha=2.7e-14, beta=4.6e-11, hibrida=2.7e-14
  pi/2   (k=32768):     K=2.7e-14, alpha=6.4e-13, beta=9.5e-13, hibrida=9.5e-13
  pi     (k=65535):     K=4.3e-08, alpha=2.4e-07, beta=2.5e-13, hibrida=2.5e-13

Recomendacion practica:
  alpha  para w < pi/4
  K      para pi/4 <= w <= 3*pi/4
  beta   para w > 3*pi/4
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np

GOERTZEL_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "goertzel",
    "description": (
        "Calcula el coeficiente DFT en una frecuencia angular w usando el algoritmo de Goertzel "
        "con formulaciones K, alpha, beta e hibrida, y compara contra numpy FFT. "
        "Devuelve el coeficiente complejo, su magnitud y el error relativo vs referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "signal": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Senal de entrada (lista de floats).",
            },
            "w": {
                "type": "number",
                "description": "Frecuencia angular en radianes (0 <= w <= pi).",
            },
            "form": {
                "type": "string",
                "enum": ["K", "alpha", "beta", "hybrid"],
                "description": "Formulacion a usar. Default: 'hybrid'.",
                "default": "hybrid",
            },
            "compare_fft": {
                "type": "boolean",
                "description": "Si true, compara contra np.fft.fft y reporta error relativo.",
                "default": True,
            },
        },
        "required": ["signal", "w"],
        "additionalProperties": False,
    },
}


def _goertzel_K(x: List[float], w: float) -> complex:
    K = 2.0 * math.cos(w)
    s1 = s2 = 0.0
    for v in x:
        s = v + K * s1 - s2
        s2 = s1
        s1 = s
    s = K * s1 - s2  # x[N] = 0
    return s - complex(math.cos(w), -math.sin(w)) * s1


def _goertzel_alpha(x: List[float], w: float) -> complex:
    al = 4.0 * math.sin(w / 2.0) ** 2
    s = d = 0.0
    for v in x:
        d = d + v - al * s
        s = s + d
    d = d - al * s
    s = s + d  # x[N] = 0
    s1 = s - d
    return s - complex(math.cos(w), -math.sin(w)) * s1


def _goertzel_beta(x: List[float], w: float) -> complex:
    be = 4.0 * math.cos(w / 2.0) ** 2
    s = d = 0.0
    for v in x:
        d = v + be * s - d
        s = d - s
    d = be * s - d
    s = d - s  # x[N] = 0
    s1 = d - s
    return s - complex(math.cos(w), -math.sin(w)) * s1


def _goertzel_hybrid(x: List[float], w: float) -> complex:
    if w < math.pi / 2.0:
        return _goertzel_alpha(x, w)
    return _goertzel_beta(x, w)


def _reference_magnitude(x: List[float], w: float) -> float:
    n = np.arange(len(x), dtype=np.longdouble)
    R = np.sum(np.asarray(x, dtype=np.longdouble) * np.exp(-1j * np.longdouble(w) * n))
    return abs(R)


def goertzel(
    signal: List[float],
    w: float,
    form: str = "hybrid",
    compare_fft: bool = True,
) -> Dict[str, Any]:
    """Ejecuta el algoritmo de Goertzel y devuelve resultados estructurados."""
    x = [float(v) for v in signal]
    n = len(x)

    if not (0.0 <= w <= math.pi):
        return {
            "error": f"w debe estar en [0, pi], se recibio {w}",
        }

    if form == "K":
        c = _goertzel_K(x, w)
    elif form == "alpha":
        c = _goertzel_alpha(x, w)
    elif form == "beta":
        c = _goertzel_beta(x, w)
    elif form == "hybrid":
        c = _goertzel_hybrid(x, w)
    else:
        return {
            "error": f"Forma desconocida: {form}. Use 'K', 'alpha', 'beta' o 'hybrid'.",
        }

    magnitude = abs(c)
    result: Dict[str, Any] = {
        "n": n,
        "w": w,
        "form": form,
        "coefficient": {"re": c.real, "im": c.imag},
        "magnitude": magnitude,
    }

    if compare_fft:
        X = np.fft.fft(x)
        k = round(w * n / (2.0 * math.pi))
        k = max(0, min(k, n - 1))
        fft_val = X[k]
        fft_mag = abs(fft_val)
        ref_mag = _reference_magnitude(x, w)
        result["fft"] = {
            "bin": k,
            "coefficient": {"re": float(fft_val.real), "im": float(fft_val.imag)},
            "magnitude": fft_mag,
        }
        result["error_vs_fft"] = abs(magnitude - fft_mag) / abs(fft_mag) if fft_mag != 0 else None
        result["error_vs_reference"] = (
            abs(magnitude - ref_mag) / abs(ref_mag) if ref_mag != 0 else None
        )
        result["reference_magnitude"] = ref_mag

    return result


def goertzel_scan(
    signal: List[float],
    forms: List[str] = ["K", "alpha", "beta", "hybrid"],
    compare_fft: bool = True,
) -> Dict[str, Any]:
    """Escanea varias frecuencias angulares tipicas y reporta errores relativos por forma."""
    x = [float(v) for v in signal]
    n = len(x)
    X = np.fft.fft(x) if compare_fft else None

    bins = [1, 3, 10, 100, 1000, n // 8, n // 4, n // 2 - 1]
    rows: List[Dict[str, Any]] = []

    for k in bins:
        if k < 0 or k >= n:
            continue
        w = 2.0 * math.pi * k / n
        ref_mag = _reference_magnitude(x, w)
        fft_mag = abs(X[k]) if compare_fft else None

        row: Dict[str, Any] = {
            "bin": k,
            "omega": w,
            "reference_magnitude": ref_mag,
        }
        if compare_fft:
            row["fft_magnitude"] = fft_mag

        for form in forms:
            if form == "K":
                c = _goertzel_K(x, w)
            elif form == "alpha":
                c = _goertzel_alpha(x, w)
            elif form == "beta":
                c = _goertzel_beta(x, w)
            elif form == "hybrid":
                c = _goertzel_hybrid(x, w)
            else:
                continue
            mag = abs(c)
            row[form] = {
                "magnitude": mag,
                "error_vs_reference": abs(mag - ref_mag) / abs(ref_mag) if ref_mag != 0 else None,
            }
            if compare_fft and fft_mag is not None:
                row[form]["error_vs_fft"] = abs(mag - fft_mag) / abs(fft_mag) if fft_mag != 0 else None

        rows.append(row)

    return {
        "n": n,
        "rows": rows,
    }