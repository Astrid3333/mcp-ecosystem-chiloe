#!/usr/bin/env python3
"""
socket_qa_engine.py

Motor de decisión para cerrar el loop generar -> evaluar -> ajustar en el
flujo de diseño de sockets protésicos (munon_a_secciones.py +
kine_to_extensiones.py).

QUÉ RESUELVE:
    Hasta ahora el flujo era "medidas -> plantilla -> geometría" sin que
    nadie revisara si esa geometría estaba bien. Este módulo NO genera
    geometría ni llama a FreeCAD directamente -- toma los resultados
    estructurados que ya devuelven las tools de verificación
    (geometric_verification, measurement_operations, spatial_query,
    contact_pressure_operations, surface_operations:thickness_analysis)
    y decide qué ajustar, con qué severidad, y cuándo NO debe auto-ajustar
    sino escalar a revisión humana.

QUÉ NO RESUELVE (a propósito):
    No decide sola en casos ambiguos o de alto riesgo clínico. Siguiendo
    el mismo criterio que ya usás en sbtcvm_convert (rechazar entradas
    ambiguas en vez de adivinar mal en silencio), este motor prefiere
    escalar antes que aplicar un ajuste que podría comprometer seguridad
    o encaje.

PUNTOS DE ENGANCHE CON LAS TOOLS REALES (a completar en tu máquina, con
FreeCAD vivo):

    1. freecad:geometric_verification -> verify_no_self_intersection,
       verify_topology
           resultado["ok"] / resultado["details"]  ->  parsear con
           extraer_issues_de_geometric_verification()

    2. freecad:contact_pressure_operations -> sample_socket_clearance +
       summarize_pressure_zones
           lista de zonas con risk_level "overlap" / "high_pressure"  ->
           extraer_issues_de_pressure_zones()

    3. freecad:surface_operations -> thickness_analysis
           mapa de espesor mínimo por cara  ->
           extraer_issues_de_thickness_analysis()

    4. kine_to_extensiones.py -> screening de pistoning (contacto con
       carga vs sin carga)  ->  extraer_issues_de_pistoning()

    5. munon_a_secciones.py -> el dict `offset_map` (índice de sección ->
       espesor mm) es el `parametros["offset_map"]` que este motor lee y
       modifica.

El ciclo completo (ciclo_qa) queda armado para que, en tu máquina, la
función `generar_fn` sea la que realmente llama a
freecad:organic_operations / freecad:surface_operations para materializar
la geometría, y `evaluar_fn` sea la que llama a las tools de verificación
de arriba y arma la lista de Issues con los extractores de este archivo.
Acá se puede probar todo el ciclo con datos sintéticos (ver __main__).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Umbrales -- ajustar según material, impresora y protocolo clínico propios.
# ---------------------------------------------------------------------------

UMBRALES = {
    "espesor_min_seguro_mm": 1.2,      # por debajo de esto, no se auto-ajusta: se escala
    "espesor_min_objetivo_mm": 2.0,    # objetivo normal (zona "transición")
    "espesor_min_carga_mm": 4.0,       # zona landmark="carga"
    "espesor_min_alivio_mm": 2.0,      # zona landmark="alivio"
    "paso_ajuste_espesor_mm": 0.5,     # cuánto se mueve el offset por iteración
    "paso_ajuste_espesor_max_mm": 1.5, # tope de un solo ajuste (evita saltos bruscos)
    "clearance_overlap_min_mm": 0.0,   # overlap = clearance negativo, siempre crítico
    "pistoning_max_mm": 4.0,           # desplazamiento carga/sin-carga aceptable sin revisar
    "max_iteraciones": 5,
}


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    tipo: str              # 'self_intersection' | 'topologia' | 'overlap' |
                            # 'high_pressure' | 'wall_thin' | 'pistoning'
    severidad: str          # 'critica' | 'alta' | 'media'
    seccion_idx: Optional[int] = None
    face_index: Optional[int] = None
    landmark: Optional[str] = None      # 'carga' | 'alivio' | None
    valor: Optional[float] = None
    objetivo: Optional[float] = None
    detalle: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Ajuste:
    parametro: str          # ruta lógica, ej. "offset_map[2]"
    delta_mm: float
    justificacion: str
    face_index: Optional[int] = None
    seccion_idx: Optional[int] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Escalamiento:
    razon: str
    issues_relacionados: list = field(default_factory=list)

    def to_dict(self):
        return {
            "razon": self.razon,
            "issues_relacionados": [i.to_dict() for i in self.issues_relacionados],
        }


@dataclass
class ResultadoCiclo:
    aprobado: bool
    iteraciones: int
    parametros_finales: dict
    historial: list                  # lista de dicts, uno por iteración
    escalamientos: list              # lista de Escalamiento, vacía si aprobado limpio


# ---------------------------------------------------------------------------
# Extractores: tool result (dict) -> list[Issue]
# Estos son los puntos de enganche reales con las tools de FreeCAD.
# ---------------------------------------------------------------------------

def extraer_issues_de_geometric_verification(resultado: dict) -> list[Issue]:
    issues = []
    if not resultado.get("ok", True):
        tipo = "self_intersection" if "intersect" in resultado.get("message", "").lower() else "topologia"
        issues.append(Issue(
            tipo=tipo,
            severidad="critica",
            detalle=resultado.get("message", "geometric_verification falló"),
        ))
    return issues


def extraer_issues_de_pressure_zones(zonas: list[dict]) -> list[Issue]:
    """
    zonas: salida de contact_pressure_operations:summarize_pressure_zones,
    se asume lista de dicts con al menos: risk_level, face_index (u otro
    identificador de zona), clearance_mm (puede ser negativo si hay overlap).
    """
    issues = []
    for z in zonas:
        risk = z.get("risk_level")
        face_index = z.get("face_index")
        landmark = z.get("landmark")
        clearance = z.get("clearance_mm")

        if risk == "overlap":
            issues.append(Issue(
                tipo="overlap",
                severidad="critica",
                face_index=face_index,
                landmark=landmark,
                valor=clearance,
                objetivo=UMBRALES["clearance_overlap_min_mm"],
                detalle=f"Interferencia socket/muñón en face_index={face_index} (clearance={clearance}mm)",
            ))
        elif risk == "high_pressure":
            issues.append(Issue(
                tipo="high_pressure",
                severidad="alta",
                face_index=face_index,
                landmark=landmark,
                valor=clearance,
                detalle=f"Zona de alta presión en face_index={face_index}",
            ))
    return issues


def extraer_issues_de_thickness_analysis(mapa_espesores: dict) -> list[Issue]:
    """
    mapa_espesores: {face_index: espesor_mm} desde
    surface_operations:thickness_analysis.
    """
    issues = []
    for face_index, espesor in mapa_espesores.items():
        if espesor < UMBRALES["espesor_min_seguro_mm"]:
            issues.append(Issue(
                tipo="wall_thin",
                severidad="critica",   # bajo el mínimo seguro -> no se auto-ajusta
                face_index=int(face_index),
                valor=espesor,
                objetivo=UMBRALES["espesor_min_seguro_mm"],
                detalle=f"Espesor {espesor}mm bajo el mínimo seguro de fabricación",
            ))
        elif espesor < UMBRALES["espesor_min_objetivo_mm"]:
            issues.append(Issue(
                tipo="wall_thin",
                severidad="media",
                face_index=int(face_index),
                valor=espesor,
                objetivo=UMBRALES["espesor_min_objetivo_mm"],
                detalle=f"Espesor {espesor}mm bajo el objetivo (pero sobre el mínimo seguro)",
            ))
    return issues


def extraer_issues_de_pistoning(desplazamiento_mm: float, seccion_idx: int, landmark: Optional[str]) -> list[Issue]:
    issues = []
    if desplazamiento_mm > UMBRALES["pistoning_max_mm"]:
        issues.append(Issue(
            tipo="pistoning",
            severidad="alta",
            seccion_idx=seccion_idx,
            landmark=landmark,
            valor=desplazamiento_mm,
            objetivo=UMBRALES["pistoning_max_mm"],
            detalle=f"Desplazamiento carga/sin-carga {desplazamiento_mm}mm excede umbral en sección {seccion_idx}",
        ))
    return issues


# ---------------------------------------------------------------------------
# Decisión: list[Issue] -> (list[Ajuste], list[Escalamiento])
# ---------------------------------------------------------------------------

def decidir_ajustes(issues: list[Issue]) -> tuple[list[Ajuste], list[Escalamiento]]:
    ajustes: list[Ajuste] = []
    escalamientos: list[Escalamiento] = []

    for issue in issues:

        # --- Casos que SIEMPRE se escalan, nunca se auto-ajustan ---
        if issue.tipo == "self_intersection":
            escalamientos.append(Escalamiento(
                razon="Auto-intersección de geometría: puede indicar un problema "
                      "estructural en el generador (loft mal formado, sección "
                      "degenerada), no un simple ajuste de parámetro.",
                issues_relacionados=[issue],
            ))
            continue

        if issue.tipo == "wall_thin" and issue.severidad == "critica":
            escalamientos.append(Escalamiento(
                razon=f"Espesor en face_index={issue.face_index} ({issue.valor}mm) "
                      f"está bajo el mínimo seguro de fabricación "
                      f"({UMBRALES['espesor_min_seguro_mm']}mm). Aumentar el offset "
                      "automáticamente acá cambia el volumen interno del socket "
                      "cerca del muñón -- requiere confirmar contra la medida real, "
                      "no solo empujar un número.",
                issues_relacionados=[issue],
            ))
            continue

        if issue.tipo == "overlap":
            # Overlap es crítico, pero a diferencia de self_intersection SÍ tiene
            # un ajuste obvio y seguro: más clearance en esa cara. Se auto-ajusta,
            # con el paso más grande porque es urgente.
            delta = min(
                abs(issue.valor or 0) + UMBRALES["paso_ajuste_espesor_mm"],
                UMBRALES["paso_ajuste_espesor_max_mm"],
            )
            ajustes.append(Ajuste(
                parametro=f"offset_map[face={issue.face_index}]",
                delta_mm=+delta,
                face_index=issue.face_index,
                justificacion=f"Overlap de {issue.valor}mm en face_index={issue.face_index}: "
                              f"se agrega clearance (+{delta}mm) para eliminar la interferencia.",
            ))
            continue

        if issue.tipo == "high_pressure":
            # No sabemos la magnitud exacta del exceso (sample_socket_clearance es
            # un proxy geométrico, no FEA) -> paso conservador, y si vuelve a salir
            # high_pressure en la misma cara tras un ajuste, eso lo decide
            # ciclo_qa() escalando por iteraciones repetidas (ver más abajo).
            paso = UMBRALES["paso_ajuste_espesor_mm"]
            if issue.landmark == "carga":
                # zona de carga: preferimos NO aflojar de más, ajuste más chico
                paso = paso * 0.5
            ajustes.append(Ajuste(
                parametro=f"offset_map[face={issue.face_index}]",
                delta_mm=+paso,
                face_index=issue.face_index,
                justificacion=f"Zona de alta presión en face_index={issue.face_index} "
                              f"(landmark={issue.landmark}): +{paso}mm de clearance local.",
            ))
            continue

        if issue.tipo == "wall_thin" and issue.severidad == "media":
            faltante = round((issue.objetivo or 0) - (issue.valor or 0), 2)
            ajustes.append(Ajuste(
                parametro=f"offset_map[face={issue.face_index}]",
                delta_mm=+min(faltante, UMBRALES["paso_ajuste_espesor_max_mm"]),
                face_index=issue.face_index,
                justificacion=f"Espesor {issue.valor}mm bajo objetivo {issue.objetivo}mm "
                              f"en face_index={issue.face_index}: +{faltante}mm.",
            ))
            continue

        if issue.tipo == "pistoning":
            if issue.landmark == "alivio":
                # en zona de alivio el desplazamiento es más tolerable; no se toca
                # sola -- se anota pero no se auto-ajusta para no reducir el alivio
                # que fue puesto ahí a propósito.
                escalamientos.append(Escalamiento(
                    razon=f"Pistoning {issue.valor}mm en sección {issue.seccion_idx}, "
                          "landmark=alivio: ajustar acá reduciría a propósito el alivio "
                          "diseñado para esa prominencia ósea. Requiere decisión clínica.",
                    issues_relacionados=[issue],
                ))
            else:
                ajustes.append(Ajuste(
                    parametro=f"offset_map[section={issue.seccion_idx}]",
                    delta_mm=-UMBRALES["paso_ajuste_espesor_mm"],  # más ajustado = menos clearance
                    seccion_idx=issue.seccion_idx,
                    justificacion=f"Pistoning {issue.valor}mm en sección {issue.seccion_idx}: "
                                  f"-{UMBRALES['paso_ajuste_espesor_mm']}mm de clearance para mejorar suspensión.",
                ))
            continue

        if issue.tipo == "topologia":
            escalamientos.append(Escalamiento(
                razon="Desviación de topología esperada (conteo de caras/aristas/vértices "
                      "no coincide) -- típicamente indica que el generador cambió de "
                      "estructura, no solo de dimensiones. Revisar antes de seguir ajustando.",
                issues_relacionados=[issue],
            ))
            continue

    return ajustes, escalamientos


def aplicar_ajustes(parametros: dict, ajustes: list[Ajuste]) -> dict:
    """
    Aplica los deltas sobre una copia de `parametros` (que se espera tenga,
    como mínimo, la clave "offset_map": {indice_o_face: espesor_mm}).
    No muta el dict original -- así cada iteración del ciclo queda con su
    propia foto de parámetros en el historial.
    """
    nuevos = json.loads(json.dumps(parametros))  # deep copy simple
    offset_map = nuevos.setdefault("offset_map", {})

    for ajuste in ajustes:
        clave = ajuste.face_index if ajuste.face_index is not None else ajuste.seccion_idx
        clave = str(clave)
        actual = offset_map.get(clave, UMBRALES["espesor_min_objetivo_mm"])
        offset_map[clave] = round(actual + ajuste.delta_mm, 2)

    return nuevos


# ---------------------------------------------------------------------------
# Ciclo completo
# ---------------------------------------------------------------------------

def ciclo_qa(
    parametros_iniciales: dict,
    generar_fn: Callable[[dict], dict],
    evaluar_fn: Callable[[dict], list[Issue]],
    max_iteraciones: int = None,
) -> ResultadoCiclo:
    """
    generar_fn(parametros) -> resultado_geometria (dict con lo que haga
        falta para que evaluar_fn pueda correr las verificaciones; en la
        integración real esto dispara las llamadas a
        freecad:organic_operations / surface_operations).

    evaluar_fn(resultado_geometria) -> list[Issue]  (en la integración
        real, esto llama a geometric_verification, contact_pressure_operations,
        surface_operations:thickness_analysis, etc. y usa los extractores
        de arriba para armar la lista).
    """
    max_iteraciones = max_iteraciones or UMBRALES["max_iteraciones"]
    parametros = parametros_iniciales
    historial = []
    issues_por_face_historicas: dict[str, int] = {}

    for i in range(1, max_iteraciones + 1):
        resultado_geometria = generar_fn(parametros)
        issues = evaluar_fn(resultado_geometria)

        if not issues:
            historial.append({"iteracion": i, "issues": [], "ajustes": [], "estado": "aprobado"})
            return ResultadoCiclo(
                aprobado=True,
                iteraciones=i,
                parametros_finales=parametros,
                historial=historial,
                escalamientos=[],
            )

        ajustes, escalamientos = decidir_ajustes(issues)

        # Si la misma cara/sección viene repitiendo el mismo tipo de issue
        # iteración tras iteración, algo no está convergiendo -> se escala
        # en vez de seguir empujando el mismo ajuste indefinidamente.
        for issue in issues:
            clave = f"{issue.tipo}:{issue.face_index}:{issue.seccion_idx}"
            issues_por_face_historicas[clave] = issues_por_face_historicas.get(clave, 0) + 1
            if issues_por_face_historicas[clave] >= 3:
                escalamientos.append(Escalamiento(
                    razon=f"'{issue.tipo}' en face={issue.face_index}/seccion={issue.seccion_idx} "
                          f"no convergió después de {issues_por_face_historicas[clave]} iteraciones "
                          "de ajuste automático. Revisar manualmente en vez de seguir empujando.",
                    issues_relacionados=[issue],
                ))
                ajustes = [a for a in ajustes if not (
                    a.face_index == issue.face_index and a.seccion_idx == issue.seccion_idx
                )]

        historial.append({
            "iteracion": i,
            "issues": [x.to_dict() for x in issues],
            "ajustes": [x.to_dict() for x in ajustes],
            "escalamientos": [x.to_dict() for x in escalamientos],
            "estado": "ajustando" if ajustes else "sin_ajustes_posibles",
        })

        if escalamientos and not ajustes:
            # nada más que se pueda hacer automáticamente esta vuelta
            return ResultadoCiclo(
                aprobado=False,
                iteraciones=i,
                parametros_finales=parametros,
                historial=historial,
                escalamientos=escalamientos,
            )

        parametros = aplicar_ajustes(parametros, ajustes)

    return ResultadoCiclo(
        aprobado=False,
        iteraciones=max_iteraciones,
        parametros_finales=parametros,
        historial=historial,
        escalamientos=[Escalamiento(
            razon=f"Se alcanzó el máximo de {max_iteraciones} iteraciones sin converger.",
        )],
    )


# ---------------------------------------------------------------------------
# Self-test con datos sintéticos (sin FreeCAD).
# Simula un socket que arranca con overlap en zona de carga y baja presión
# en zona de alivio, y converge en 2-3 iteraciones. Después simula un caso
# que debe escalar (wall_thin crítico) para mostrar que el motor no
# auto-ajusta todo a ciegas.
# ---------------------------------------------------------------------------

def _demo_generar_fn(parametros: dict) -> dict:
    # En la integración real: llama a freecad:organic_operations
    # (cross_section_stack) + surface_operations (offset_surface) con
    # `parametros["offset_map"]`, y devuelve nombres de objetos FreeCAD
    # para que evaluar_fn corra las verificaciones sobre ellos.
    return {"offset_map_aplicado": parametros.get("offset_map", {})}


def _demo_evaluar_fn_factory():
    """
    Devuelve una evaluar_fn con estado interno para simular convergencia:
    la primera vuelta reporta overlap en face 0 (landmark carga) y
    high_pressure en face 2 (landmark alivio); las siguientes vueltas
    reflejan que el offset_map ya corregido reduce el problema.
    """
    llamada = {"n": 0}

    def evaluar_fn(resultado_geometria: dict) -> list[Issue]:
        llamada["n"] += 1
        offset_map = resultado_geometria.get("offset_map_aplicado", {})
        issues = []

        clearance_face0 = -1.0 + float(offset_map.get("0", 0))
        if clearance_face0 < 0:
            issues.extend(extraer_issues_de_pressure_zones([
                {"risk_level": "overlap", "face_index": 0, "landmark": "carga", "clearance_mm": round(clearance_face0, 2)}
            ]))

        espesor_face2 = 1.5 + float(offset_map.get("2", 0))
        if espesor_face2 < UMBRALES["espesor_min_alivio_mm"]:
            issues.extend(extraer_issues_de_pressure_zones([
                {"risk_level": "high_pressure", "face_index": 2, "landmark": "alivio", "clearance_mm": round(espesor_face2, 2)}
            ]))

        return issues

    return evaluar_fn


def _demo_caso_convergente():
    print("=" * 70)
    print("DEMO 1: caso que converge (overlap en carga + presión en alivio)")
    print("=" * 70)
    parametros_iniciales = {"offset_map": {"0": 0.0, "1": 3.0, "2": 0.0, "3": 3.0}}
    resultado = ciclo_qa(
        parametros_iniciales,
        generar_fn=_demo_generar_fn,
        evaluar_fn=_demo_evaluar_fn_factory(),
    )
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    print("parametros_finales:", json.dumps(resultado.parametros_finales, indent=2, ensure_ascii=False))
    for h in resultado.historial:
        print(f"\n-- iteración {h['iteracion']} ({h['estado']}) --")
        for iss in h["issues"]:
            print(f"   issue: {iss['tipo']} severidad={iss['severidad']} face={iss['face_index']} detalle={iss['detalle']}")
        for aj in h["ajustes"]:
            print(f"   ajuste: {aj['parametro']} delta={aj['delta_mm']:+}mm -- {aj['justificacion']}")


def _demo_caso_escala():
    print("\n" + "=" * 70)
    print("DEMO 2: caso que debe escalar (espesor bajo mínimo seguro)")
    print("=" * 70)

    def generar_fn(parametros):
        return {}

    def evaluar_fn(resultado_geometria):
        return extraer_issues_de_thickness_analysis({"5": 0.8})  # bajo el mínimo seguro (1.2mm)

    resultado = ciclo_qa({"offset_map": {}}, generar_fn, evaluar_fn)
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    for esc in resultado.escalamientos:
        print(f"ESCALAMIENTO: {esc.razon}")


if __name__ == "__main__":
    _demo_caso_convergente()
    _demo_caso_escala()
