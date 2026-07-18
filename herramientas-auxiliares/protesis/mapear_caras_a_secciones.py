#!/usr/bin/env python3
"""
mapear_caras_a_secciones.py

Resuelve el problema anotado en munon_a_secciones.py: el offset_map que
generan las tools usa 'face_index' como clave, pero no hay garantía de que
face_index N en el sólido de FreeCAD (post cross_section_stack) corresponda
a la sección N de las medidas originales -- depende de cómo OCC tesela el
loft.

ENFOQUE: mapeo GEOMÉTRICO, no por orden. Para cada cara del sólido se
compara la coordenada del centroide sobre el eje del stack contra la
posición mm de cada sección medida, y se asigna la sección más cercana.
Si una cara queda casi a mitad de camino entre dos secciones (dentro de
`umbral_ambiguedad_mm`), NO se asigna automáticamente -- se reporta como
ambigua para revisión manual. Mismo criterio que sbtcvm_convert: fallar
visible en vez de adivinar en silencio.

También distingue caras "tapa" (normal ~paralela al eje, extremos
proximal/distal) de caras "laterales" (normal ~perpendicular al eje,
la piel del socket), porque el offset variable por landmark tiene sentido
sobre todo en las laterales.

ENTRADA ESPERADA:
    `caras`: lista de dicts, uno por cara, con AL MENOS un identificador
    de índice y coordenadas de centroide. Se acepta variación de nombres
    de campo (ver _extraer_centroid / _extraer_normal / _extraer_indice)
    porque el schema exacto que devuelve freecad:measurement_operations
    (list_faces) o freecad:geometric_verification no se pudo verificar
    en este entorno (sin FreeCAD vivo) -- si algún campo no matchea, esto
    falla con un error explícito listando las claves disponibles, en vez
    de asignar cualquier cosa.

    `posiciones_referencia`: lista de dicts como los que ya produce
    munon_a_secciones.py, uno por sección medida:
        {"seccion_idx": int, "position_mm": float, "landmark": str|None}

USO TÍPICO (una vez conectado a FreeCAD real):
    1. Generar el sólido con freecad:organic_operations (cross_section_stack).
    2. Pedir freecad:measurement_operations -> list_faces sobre ese sólido.
    3. Pasar el resultado + las MEDICIONES originales (con landmark) a
       clasificar_caras().
    4. Usar el mapeo resultante para traducir face_index -> landmark antes
       de llamar a los extractores de socket_qa_engine.py (que ya esperan
       'landmark' en cada zona/issue).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


EJE_A_INDICE = {"x": 0, "y": 1, "z": 2}


class CampoNoEncontrado(ValueError):
    pass


def _extraer_indice(cara: dict) -> int:
    for clave in ("face_index", "index", "faceIndex", "i"):
        if clave in cara:
            return int(cara[clave])
    raise CampoNoEncontrado(
        f"No encontré índice de cara en {list(cara.keys())}. "
        "Revisar el schema real que devuelve la tool y agregar la clave "
        "correcta a _extraer_indice()."
    )


def _extraer_centroid(cara: dict) -> tuple[float, float, float]:
    for clave in ("centroid", "center", "centre_of_mass", "center_of_mass", "com"):
        if clave in cara:
            v = cara[clave]
            if isinstance(v, dict):
                return (v.get("x", v.get("X")), v.get("y", v.get("Y")), v.get("z", v.get("Z")))
            return tuple(v)
    raise CampoNoEncontrado(
        f"No encontré centroide de cara en {list(cara.keys())}. "
        "Revisar el schema real que devuelve la tool y agregar la clave "
        "correcta a _extraer_centroid()."
    )


def _extraer_normal(cara: dict) -> Optional[tuple[float, float, float]]:
    for clave in ("normal", "face_normal", "normal_vector"):
        if clave in cara:
            v = cara[clave]
            if isinstance(v, dict):
                return (v.get("x", v.get("X")), v.get("y", v.get("Y")), v.get("z", v.get("Z")))
            return tuple(v)
    return None  # la normal es opcional -- sin ella no se distingue tapa/lateral


@dataclass
class ClasificacionCara:
    face_index: int
    seccion_idx: int
    landmark: Optional[str]
    distancia_mm: float
    es_tapa: bool

    def to_dict(self):
        return asdict(self)


@dataclass
class CaraAmbigua:
    face_index: int
    coord_eje_mm: float
    candidatos: list  # [(seccion_idx, distancia_mm), ...] los dos más cercanos
    razon: str

    def to_dict(self):
        return {
            "face_index": self.face_index,
            "coord_eje_mm": self.coord_eje_mm,
            "candidatos": self.candidatos,
            "razon": self.razon,
        }


def clasificar_caras(
    caras: list[dict],
    posiciones_referencia: list[dict],
    eje: str = "z",
    umbral_ambiguedad_mm: float = 5.0,
    tolerancia_cap_normal: float = 0.9,
) -> tuple[dict[int, ClasificacionCara], list[CaraAmbigua]]:
    """
    Devuelve (mapeo, ambiguas):
        mapeo: {face_index: ClasificacionCara}  -- solo caras asignadas con confianza
        ambiguas: lista de CaraAmbigua  -- caras que NO se asignaron automáticamente
    """
    if eje not in EJE_A_INDICE:
        raise ValueError(f"eje debe ser 'x', 'y' o 'z', recibido: {eje!r}")
    idx_eje = EJE_A_INDICE[eje]

    if not posiciones_referencia:
        raise ValueError("posiciones_referencia está vacío -- no hay nada contra qué clasificar.")

    mapeo: dict[int, ClasificacionCara] = {}
    ambiguas: list[CaraAmbigua] = []

    for cara in caras:
        face_index = _extraer_indice(cara)
        centroid = _extraer_centroid(cara)
        normal = _extraer_normal(cara)
        coord = centroid[idx_eje]

        distancias = sorted(
            (
                (abs(coord - ref["position_mm"]), ref)
                for ref in posiciones_referencia
            ),
            key=lambda t: t[0],
        )

        d_mas_cercana, ref_mas_cercana = distancias[0]

        if len(distancias) > 1:
            d_segunda, ref_segunda = distancias[1]
            if (d_segunda - d_mas_cercana) < umbral_ambiguedad_mm:
                ambiguas.append(CaraAmbigua(
                    face_index=face_index,
                    coord_eje_mm=round(coord, 2),
                    candidatos=[
                        (ref_mas_cercana["seccion_idx"], round(d_mas_cercana, 2)),
                        (ref_segunda["seccion_idx"], round(d_segunda, 2)),
                    ],
                    razon=f"Distancia a sección {ref_mas_cercana['seccion_idx']} "
                          f"({d_mas_cercana:.2f}mm) y a sección {ref_segunda['seccion_idx']} "
                          f"({d_segunda:.2f}mm) difieren menos que el umbral "
                          f"({umbral_ambiguedad_mm}mm). No se asigna sola.",
                ))
                continue

        es_tapa = False
        if normal is not None:
            componente_axial = abs(normal[idx_eje])
            es_tapa = componente_axial > tolerancia_cap_normal

        mapeo[face_index] = ClasificacionCara(
            face_index=face_index,
            seccion_idx=ref_mas_cercana["seccion_idx"],
            landmark=ref_mas_cercana.get("landmark"),
            distancia_mm=round(d_mas_cercana, 2),
            es_tapa=es_tapa,
        )

    return mapeo, ambiguas


def posiciones_referencia_desde_mediciones(mediciones: list[dict]) -> list[dict]:
    """
    Adaptador directo desde el formato MEDICIONES de munon_a_secciones.py
    (lista de {"position_mm", "ap_mm", "ml_mm", "landmark"}) al formato
    que espera clasificar_caras().
    """
    return [
        {
            "seccion_idx": i,
            "position_mm": m["position_mm"],
            "landmark": m.get("landmark"),
        }
        for i, m in enumerate(mediciones)
    ]


def enriquecer_zonas_con_landmark(zonas: list[dict], mapeo: dict[int, ClasificacionCara]) -> list[dict]:
    """
    Toma la salida cruda de contact_pressure_operations:summarize_pressure_zones
    (zonas con face_index pero sin landmark confiable) y le agrega
    seccion_idx/landmark usando el mapeo geométrico, en vez de lo que haya
    reportado la tool por su cuenta.

    Zonas cuyo face_index no está en `mapeo` (porque la cara quedó marcada
    ambigua) se devuelven con landmark=None y una nota -- no se inventa.
    """
    enriquecidas = []
    for z in zonas:
        z = dict(z)
        clasif = mapeo.get(z.get("face_index"))
        if clasif is not None:
            z["seccion_idx"] = clasif.seccion_idx
            z["landmark"] = clasif.landmark
            z["es_tapa"] = clasif.es_tapa
        else:
            z["seccion_idx"] = None
            z["landmark"] = None
            z["_nota"] = "face_index sin clasificación confiable (cara ambigua o fuera del mapeo)"
        enriquecidas.append(z)
    return enriquecidas


# ---------------------------------------------------------------------------
# Self-test con datos sintéticos (sin FreeCAD)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    # Mismas posiciones que MEDICIONES de munon_a_secciones.py
    mediciones_ejemplo = [
        {"position_mm": 0, "landmark": "carga"},
        {"position_mm": 20, "landmark": None},
        {"position_mm": 40, "landmark": "alivio"},
        {"position_mm": 60, "landmark": None},
        {"position_mm": 80, "landmark": None},
        {"position_mm": 100, "landmark": "alivio"},
    ]
    posiciones_ref = posiciones_referencia_desde_mediciones(mediciones_ejemplo)

    # Caras sintéticas: una lateral cerca de cada sección (offset chico),
    # dos tapas en los extremos (normal paralela al eje), y una cara puesta
    # deliberadamente a mitad de camino entre dos secciones para probar
    # la detección de ambigüedad.
    caras_ejemplo = [
        {"face_index": 0, "centroid": [45, 0, 0], "normal": [1, 0, 0]},   # lateral cerca de sección 0 (pos=0)
        {"face_index": 1, "centroid": [45, 0, 19], "normal": [1, 0, 0]},  # lateral cerca de sección 1 (pos=20)
        {"face_index": 2, "centroid": [40, 0, 41], "normal": [1, 0, 0]},  # lateral cerca de sección 2 (pos=40, alivio)
        {"face_index": 3, "centroid": [36, 0, 59], "normal": [1, 0, 0]},  # lateral cerca de sección 3 (pos=60)
        {"face_index": 4, "centroid": [33, 0, 81], "normal": [1, 0, 0]},  # lateral cerca de sección 4 (pos=80)
        {"face_index": 5, "centroid": [29, 0, 99], "normal": [1, 0, 0]},  # lateral cerca de sección 5 (pos=100, alivio)
        {"face_index": 6, "centroid": [0, 0, 0], "normal": [0, 0, -1]},   # tapa proximal
        {"face_index": 7, "centroid": [0, 0, 100], "normal": [0, 0, 1]},  # tapa distal
        {"face_index": 8, "centroid": [38, 0, 30], "normal": [1, 0, 0]},  # AMBIGUA: entre sección 1 (20) y 2 (40)
    ]

    mapeo, ambiguas = clasificar_caras(caras_ejemplo, posiciones_ref, eje="z")

    print("=" * 70)
    print("MAPEO CONFIABLE (face_index -> sección/landmark)")
    print("=" * 70)
    for face_index, clasif in sorted(mapeo.items()):
        print(f"  face {face_index}: seccion_idx={clasif.seccion_idx} "
              f"landmark={clasif.landmark} distancia={clasif.distancia_mm}mm "
              f"es_tapa={clasif.es_tapa}")

    print("\n" + "=" * 70)
    print("CARAS AMBIGUAS (requieren revisión manual)")
    print("=" * 70)
    for amb in ambiguas:
        print(f"  face {amb.face_index}: {amb.razon}")

    print("\n" + "=" * 70)
    print("Ejemplo de enriquecer_zonas_con_landmark()")
    print("=" * 70)
    zonas_crudas = [
        {"risk_level": "overlap", "face_index": 0, "clearance_mm": -0.8},
        {"risk_level": "high_pressure", "face_index": 2, "clearance_mm": 1.1},
        {"risk_level": "high_pressure", "face_index": 8, "clearance_mm": 0.9},  # cara ambigua
    ]
    zonas_enriquecidas = enriquecer_zonas_con_landmark(zonas_crudas, mapeo)
    print(json.dumps(zonas_enriquecidas, indent=2, ensure_ascii=False))
