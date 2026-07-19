#!/usr/bin/env python3
"""
socket_qa_engine.py

Motor de decisión para cerrar el loop generar -> evaluar -> ajustar en el
flujo de diseño de sockets protésicos (munon_a_secciones.py +
kine_to_extensiones.py + mapear_caras_a_secciones.py).

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

FIX (sobre la versión anterior): offset_map se indexa por seccion_idx,
no por face_index.
    munon_a_secciones.py ya avisa en su propio docstring: "verificar en
    FreeCAD cómo quedan numeradas las caras tras el cross_section_stack
    antes de aplicar el offset, puede no ser 1:1 con el índice de sección
    de medición". mapear_caras_a_secciones.py existe justamente para
    resolver eso -- pero la versión anterior de este motor construía los
    Issues de overlap/high_pressure/wall_thin solo con `face_index` y
    nunca leía el `seccion_idx` que ya venía resuelto (por ejemplo, desde
    enriquecer_zonas_con_landmark). Como offset_surface retesela el
    sólido en cada iteración, face_index NO es estable de una iteración a
    la otra: face_index=4 en la iteración 1 puede corresponder a una cara
    completamente distinta que face_index=4 en la iteración 2. Indexar
    offset_map (que es fundamentalmente "espesor por sección medida", ver
    munon_a_secciones.py) con una clave inestable puede terminar
    empujando el offset de la sección equivocada sin que nada lo avise.

    Ahora: los extractores que vienen de tools indexadas por cara
    (pressure_zones, thickness_analysis) reciben opcionalmente el
    `mapeo` que devuelve mapear_caras_a_secciones.clasificar_caras(), y
    resuelven seccion_idx ANTES de armar el Issue. face_index se
    conserva solo como dato de diagnóstico/trazabilidad en el Issue,
    nunca como clave. Si una cara no se puede resolver con confianza
    (fuera del mapeo, o marcada ambigua por clasificar_caras), el issue
    correspondiente escala en vez de ajustar con una clave adivinada --
    aplicar_ajustes ahora sólo acepta seccion_idx y revienta fuerte
    (ValueError) si algún Ajuste llega sin ella, en vez de caer de nuevo
    en face_index como fallback silencioso.

PUNTOS DE ENGANCHE CON LAS TOOLS REALES (a completar en tu máquina, con
FreeCAD vivo):

    1. freecad:geometric_verification -> verify_no_self_intersection,
       verify_topology
           resultado["ok"] / resultado["details"]  ->  parsear con
           extraer_issues_de_geometric_verification()

    2. freecad:measurement_operations -> list_faces  +
       mapear_caras_a_secciones.clasificar_caras()
           corré esto ANTES que los extractores de abajo, con las mismas
           MEDICIONES (via posiciones_referencia_desde_mediciones) que
           usaste para generar el socket. El `mapeo` resultante se pasa
           a los extractores de (3) y (4).

    3. freecad:contact_pressure_operations -> sample_socket_clearance +
       summarize_pressure_zones
           lista de zonas con risk_level "overlap" / "high_pressure"  ->
           extraer_issues_de_pressure_zones(zonas, mapeo)

    4. freecad:surface_operations -> thickness_analysis
           mapa de espesor mínimo por cara  ->
           extraer_issues_de_thickness_analysis(mapa, mapeo)

    5. kine_to_extensiones.py -> screening de pistoning (contacto con
       carga vs sin carga)  ->  extraer_issues_de_pistoning()
           (ya reporta seccion_idx directo, no pasa por face_index)

    6. munon_a_secciones.py -> el dict `offset_map` (índice de SECCIÓN ->
       espesor mm) es el `parametros["offset_map"]` que este motor lee y
       modifica.

El ciclo completo (ciclo_qa) queda armado para que, en tu máquina, la
función `generar_fn` sea la que realmente llama a
freecad:organic_operations / freecad:surface_operations para materializar
la geometría, y `evaluar_fn` sea la que llama a measurement_operations +
clasificar_caras() + las tools de verificación de arriba, y arma la lista
de Issues con los extractores de este archivo. Acá se puede probar todo
el ciclo con datos sintéticos (ver __main__).
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
    tipo: str               # 'self_intersection' | 'topologia' | 'overlap' |
                             # 'high_pressure' | 'wall_thin' | 'pistoning'
    severidad: str           # 'critica' | 'alta' | 'media'
    seccion_idx: Optional[int] = None   # clave estable -- índice en MEDICIONES
    face_index: Optional[int] = None    # solo diagnóstico, NUNCA se usa como clave
    landmark: Optional[str] = None      # 'carga' | 'alivio' | None
    valor: Optional[float] = None
    objetivo: Optional[float] = None
    detalle: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Ajuste:
    parametro: str          # ruta lógica, ej. "offset_map[seccion=2]"
    delta_mm: float
    seccion_idx: int         # obligatoria -- offset_map se indexa por sección, no por cara
    justificacion: str
    face_index: Optional[int] = None    # solo trazabilidad de qué cara originó el ajuste

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
# Resolución face_index -> seccion_idx usando el mapeo geométrico de
# mapear_caras_a_secciones.clasificar_caras().
# ---------------------------------------------------------------------------

def _resolver_seccion(face_index: Optional[int], mapeo: Optional[dict]) -> tuple[Optional[int], Optional[str]]:
    """
    Acepta un `mapeo` como el que devuelve clasificar_caras() (dict de
    face_index -> ClasificacionCara) o, para no atar este módulo a un
    tipo concreto, también dict de face_index -> dict con al menos
    'seccion_idx' / 'landmark'. Si no hay mapeo, o la cara no está en él
    (quedó ambigua o fuera de rango), devuelve (None, None) -- nunca
    inventa un seccion_idx a partir del face_index.
    """
    if mapeo is None or face_index is None:
        return None, None
    clasif = mapeo.get(face_index)
    if clasif is None:
        return None, None
    seccion_idx = getattr(clasif, "seccion_idx", None)
    landmark = getattr(clasif, "landmark", None)
    if isinstance(clasif, dict):
        seccion_idx = clasif.get("seccion_idx", seccion_idx)
        landmark = clasif.get("landmark", landmark)
    return seccion_idx, landmark


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


def extraer_issues_de_pressure_zones(zonas: list[dict], mapeo: Optional[dict] = None) -> list[Issue]:
    """
    zonas: salida de contact_pressure_operations:summarize_pressure_zones
    (o de mapear_caras_a_secciones.enriquecer_zonas_con_landmark(), que ya
    trae seccion_idx/landmark resueltos -- si una zona ya viene con
    'seccion_idx', se respeta y no se vuelve a resolver por mapeo).

    Se espera lista de dicts con al menos: risk_level, face_index,
    clearance_mm (puede ser negativo si hay overlap).
    """
    issues = []
    for z in zonas:
        risk = z.get("risk_level")
        face_index = z.get("face_index")
        clearance = z.get("clearance_mm")

        if "seccion_idx" in z:
            seccion_idx = z.get("seccion_idx")
            landmark = z.get("landmark")
        else:
            seccion_idx, landmark = _resolver_seccion(face_index, mapeo)

        sin_resolver = seccion_idx is None
        nota = (
            f" [sección sin resolver para face_index={face_index}: no está en el "
            "mapeo geométrico o la cara quedó marcada ambigua -- correr "
            "mapear_caras_a_secciones.clasificar_caras() antes de ajustar]"
            if sin_resolver else ""
        )

        if risk == "overlap":
            issues.append(Issue(
                tipo="overlap",
                severidad="critica",
                seccion_idx=seccion_idx,
                face_index=face_index,
                landmark=landmark,
                valor=clearance,
                objetivo=UMBRALES["clearance_overlap_min_mm"],
                detalle=f"Interferencia socket/muñón en face_index={face_index} "
                        f"(clearance={clearance}mm){nota}",
            ))
        elif risk == "high_pressure":
            issues.append(Issue(
                tipo="high_pressure",
                severidad="alta",
                seccion_idx=seccion_idx,
                face_index=face_index,
                landmark=landmark,
                valor=clearance,
                detalle=f"Zona de alta presión en face_index={face_index}{nota}",
            ))
    return issues


def extraer_issues_de_thickness_analysis(mapa_espesores: dict, mapeo: Optional[dict] = None) -> list[Issue]:
    """
    mapa_espesores: {face_index: espesor_mm} desde
    surface_operations:thickness_analysis.
    """
    issues = []
    for face_index_raw, espesor in mapa_espesores.items():
        face_index = int(face_index_raw)
        seccion_idx, _landmark = _resolver_seccion(face_index, mapeo)
        sin_resolver = seccion_idx is None
        nota = (
            f" [sección sin resolver para face_index={face_index}]" if sin_resolver else ""
        )

        if espesor < UMBRALES["espesor_min_seguro_mm"]:
            issues.append(Issue(
                tipo="wall_thin",
                severidad="critica",   # bajo el mínimo seguro -> no se auto-ajusta, siempre
                seccion_idx=seccion_idx,
                face_index=face_index,
                valor=espesor,
                objetivo=UMBRALES["espesor_min_seguro_mm"],
                detalle=f"Espesor {espesor}mm bajo el mínimo seguro de fabricación{nota}",
            ))
        elif espesor < UMBRALES["espesor_min_objetivo_mm"]:
            issues.append(Issue(
                tipo="wall_thin",
                severidad="media",
                seccion_idx=seccion_idx,
                face_index=face_index,
                valor=espesor,
                objetivo=UMBRALES["espesor_min_objetivo_mm"],
                detalle=f"Espesor {espesor}mm bajo el objetivo (pero sobre el mínimo seguro){nota}",
            ))
    return issues


def extraer_issues_de_pistoning(desplazamiento_mm: float, seccion_idx: int, landmark: Optional[str]) -> list[Issue]:
    # Ya viene indexado por seccion_idx desde kine_to_extensiones.py -- no
    # pasa por face_index en ningún momento, no necesita mapeo.
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
            seccion_txt = issue.seccion_idx if issue.seccion_idx is not None else "(sin resolver)"
            escalamientos.append(Escalamiento(
                razon=f"Espesor en sección {seccion_txt} (face_index={issue.face_index}, "
                      f"{issue.valor}mm) está bajo el mínimo seguro de fabricación "
                      f"({UMBRALES['espesor_min_seguro_mm']}mm). Aumentar el offset "
                      "automáticamente acá cambia el volumen interno del socket "
                      "cerca del muñón -- requiere confirmar contra la medida real, "
                      "no solo empujar un número.",
                issues_relacionados=[issue],
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

        # --- A partir de acá, todo lo que sigue toca offset_map, que está
        # indexado por seccion_idx (estable), no por face_index (inestable
        # entre teselaciones -- ver docstring del módulo). Si no hay una
        # seccion_idx resuelta con confianza, no se adivina: se escala. ---
        if issue.tipo in ("overlap", "high_pressure", "wall_thin") and issue.seccion_idx is None:
            escalamientos.append(Escalamiento(
                razon=f"'{issue.tipo}' en face_index={issue.face_index}: no se pudo resolver "
                      "a qué sección corresponde (cara fuera del mapeo geométrico o marcada "
                      "ambigua por mapear_caras_a_secciones.clasificar_caras()). Ajustar "
                      "offset_map con un face_index no confirmado puede tocar la sección "
                      "equivocada -- la numeración de caras no es estable entre iteraciones.",
                issues_relacionados=[issue],
            ))
            continue

        if issue.tipo == "overlap":
            # Overlap es crítico, pero a diferencia de self_intersection SÍ tiene
            # un ajuste obvio y seguro: más clearance en esa sección. Se auto-ajusta,
            # con el paso más grande porque es urgente.
            delta = min(
                abs(issue.valor or 0) + UMBRALES["paso_ajuste_espesor_mm"],
                UMBRALES["paso_ajuste_espesor_max_mm"],
            )
            ajustes.append(Ajuste(
                parametro=f"offset_map[seccion={issue.seccion_idx}]",
                delta_mm=+delta,
                seccion_idx=issue.seccion_idx,
                face_index=issue.face_index,
                justificacion=f"Overlap de {issue.valor}mm en sección {issue.seccion_idx} "
                              f"(face_index={issue.face_index}): se agrega clearance "
                              f"(+{delta}mm) para eliminar la interferencia.",
            ))
            continue

        if issue.tipo == "high_pressure":
            # No sabemos la magnitud exacta del exceso (sample_socket_clearance es
            # un proxy geométrico, no FEA) -> paso conservador, y si vuelve a salir
            # high_pressure en la misma sección tras un ajuste, eso lo decide
            # ciclo_qa() escalando por iteraciones repetidas (ver más abajo).
            paso = UMBRALES["paso_ajuste_espesor_mm"]
            if issue.landmark == "carga":
                # zona de carga: preferimos NO aflojar de más, ajuste más chico
                paso = paso * 0.5
            ajustes.append(Ajuste(
                parametro=f"offset_map[seccion={issue.seccion_idx}]",
                delta_mm=+paso,
                seccion_idx=issue.seccion_idx,
                face_index=issue.face_index,
                justificacion=f"Zona de alta presión en sección {issue.seccion_idx} "
                              f"(face_index={issue.face_index}, landmark={issue.landmark}): "
                              f"+{paso}mm de clearance local.",
            ))
            continue

        if issue.tipo == "wall_thin" and issue.severidad == "media":
            faltante = round((issue.objetivo or 0) - (issue.valor or 0), 2)
            ajustes.append(Ajuste(
                parametro=f"offset_map[seccion={issue.seccion_idx}]",
                delta_mm=+min(faltante, UMBRALES["paso_ajuste_espesor_max_mm"]),
                seccion_idx=issue.seccion_idx,
                face_index=issue.face_index,
                justificacion=f"Espesor {issue.valor}mm bajo objetivo {issue.objetivo}mm "
                              f"en sección {issue.seccion_idx} (face_index={issue.face_index}): "
                              f"+{faltante}mm.",
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
                    parametro=f"offset_map[seccion={issue.seccion_idx}]",
                    delta_mm=-UMBRALES["paso_ajuste_espesor_mm"],  # más ajustado = menos clearance
                    seccion_idx=issue.seccion_idx,
                    justificacion=f"Pistoning {issue.valor}mm en sección {issue.seccion_idx}: "
                                  f"-{UMBRALES['paso_ajuste_espesor_mm']}mm de clearance para mejorar suspensión.",
                ))
            continue

    return ajustes, escalamientos


def aplicar_ajustes(parametros: dict, ajustes: list[Ajuste]) -> dict:
    """
    Aplica los deltas sobre una copia de `parametros` (que se espera tenga,
    como mínimo, la clave "offset_map": {seccion_idx: espesor_mm}).
    No muta el dict original -- así cada iteración del ciclo queda con su
    propia foto de parámetros en el historial.

    offset_map se indexa SIEMPRE por seccion_idx. Si algún Ajuste llega sin
    seccion_idx resuelta, es un bug en decidir_ajustes (que debería haber
    escalado en vez de producir ese Ajuste) -- se revienta acá en vez de
    caer de nuevo en face_index como fallback silencioso, que es
    precisamente el bug que este módulo corrige.
    """
    nuevos = json.loads(json.dumps(parametros))  # deep copy simple
    offset_map = nuevos.setdefault("offset_map", {})

    for ajuste in ajustes:
        if ajuste.seccion_idx is None:
            raise ValueError(
                f"Ajuste sin seccion_idx resuelta ({ajuste.parametro!r}, "
                f"face_index={ajuste.face_index}): no se puede aplicar sobre "
                "offset_map sin saber qué sección tocar. decidir_ajustes() "
                "debería haber escalado este caso en vez de producir el Ajuste."
            )
        clave = str(ajuste.seccion_idx)
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
        real, esto llama a measurement_operations:list_faces +
        mapear_caras_a_secciones.clasificar_caras() para obtener el
        `mapeo` de esa iteración -- que cambia si la geometría se
        reteseló -- y después a geometric_verification,
        contact_pressure_operations, surface_operations:thickness_analysis,
        pasando ese `mapeo` a los extractores de arriba).
    """
    max_iteraciones = max_iteraciones or UMBRALES["max_iteraciones"]
    parametros = parametros_iniciales
    historial = []
    issues_por_seccion_historicas: dict[str, int] = {}

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

        # Si la misma sección viene repitiendo el mismo tipo de issue
        # iteración tras iteración, algo no está convergiendo -> se escala
        # en vez de seguir empujando el mismo ajuste indefinidamente.
        # Clave por seccion_idx (estable), no por face_index (que puede
        # cambiar de una iteración a otra aunque sea "la misma" cara real).
        for issue in issues:
            clave = f"{issue.tipo}:{issue.seccion_idx}"
            issues_por_seccion_historicas[clave] = issues_por_seccion_historicas.get(clave, 0) + 1
            if issues_por_seccion_historicas[clave] >= 3:
                escalamientos.append(Escalamiento(
                    razon=f"'{issue.tipo}' en sección {issue.seccion_idx} no convergió "
                          f"después de {issues_por_seccion_historicas[clave]} iteraciones "
                          "de ajuste automático. Revisar manualmente en vez de seguir empujando.",
                    issues_relacionados=[issue],
                ))
                ajustes = [a for a in ajustes if a.seccion_idx != issue.seccion_idx]

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
# ---------------------------------------------------------------------------

def _demo_generar_fn(parametros: dict) -> dict:
    return {"offset_map_aplicado": parametros.get("offset_map", {})}


def _demo_caso_convergente():
    print("=" * 70)
    print("DEMO 1: caso que converge (overlap en carga + presión en alivio)")
    print("=" * 70)

    # mapeo geométrico "limpio": en este caso face_index coincide con
    # seccion_idx, como en el self-test de mapear_caras_a_secciones.py.
    mapeo = {0: {"seccion_idx": 0, "landmark": "carga"}, 2: {"seccion_idx": 2, "landmark": "alivio"}}
    llamada = {"n": 0}

    def evaluar_fn(resultado_geometria):
        llamada["n"] += 1
        offset_map = resultado_geometria.get("offset_map_aplicado", {})
        issues = []
        clearance_face0 = -1.0 + float(offset_map.get("0", 0))
        if clearance_face0 < 0:
            issues.extend(extraer_issues_de_pressure_zones(
                [{"risk_level": "overlap", "face_index": 0, "clearance_mm": round(clearance_face0, 2)}],
                mapeo=mapeo,
            ))
        espesor_face2 = 1.5 + float(offset_map.get("2", 0))
        if espesor_face2 < UMBRALES["espesor_min_alivio_mm"]:
            issues.extend(extraer_issues_de_pressure_zones(
                [{"risk_level": "high_pressure", "face_index": 2, "clearance_mm": round(espesor_face2, 2)}],
                mapeo=mapeo,
            ))
        return issues

    parametros_iniciales = {"offset_map": {"0": 0.0, "1": 3.0, "2": 0.0, "3": 3.0}}
    resultado = ciclo_qa(parametros_iniciales, generar_fn=_demo_generar_fn, evaluar_fn=evaluar_fn)
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    print("parametros_finales:", json.dumps(resultado.parametros_finales, indent=2, ensure_ascii=False))
    for h in resultado.historial:
        print(f"\n-- iteración {h['iteracion']} ({h['estado']}) --")
        for iss in h["issues"]:
            print(f"   issue: {iss['tipo']} severidad={iss['severidad']} seccion={iss['seccion_idx']} detalle={iss['detalle']}")
        for aj in h["ajustes"]:
            print(f"   ajuste: {aj['parametro']} delta={aj['delta_mm']:+}mm -- {aj['justificacion']}")


def _demo_caso_escala():
    print("\n" + "=" * 70)
    print("DEMO 2: caso que debe escalar (espesor bajo mínimo seguro)")
    print("=" * 70)

    def generar_fn(parametros):
        return {}

    def evaluar_fn(resultado_geometria):
        # bajo el mínimo seguro (1.2mm) -- escala SIEMPRE, con o sin mapeo,
        # porque wall_thin/critica nunca se auto-ajusta.
        return extraer_issues_de_thickness_analysis({"5": 0.8}, mapeo=None)

    resultado = ciclo_qa({"offset_map": {}}, generar_fn, evaluar_fn)
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    for esc in resultado.escalamientos:
        print(f"ESCALAMIENTO: {esc.razon}")


def _demo_caso_face_index_inestable():
    print("\n" + "=" * 70)
    print("DEMO 3: face_index=4 se repite entre iteraciones pero NO es la")
    print("misma sección -- retesela y apunta primero a sección 0 (carga,")
    print("z=0) y después a sección 3 (z=62). Con el fix, cada una se")
    print("ajusta por separado en offset_map; nunca se colapsan en una")
    print("sola clave '4'.")
    print("=" * 70)

    llamada = {"n": 0}

    def generar_fn(parametros):
        return {"offset_map_aplicado": parametros.get("offset_map", {})}

    def evaluar_fn(resultado_geometria):
        llamada["n"] += 1
        offset_map = resultado_geometria.get("offset_map_aplicado", {})

        if llamada["n"] == 1:
            # Primera tesela: face_index=4 es, geométricamente, la sección 0
            # (carga, z=0mm) -- con overlap.
            mapeo = {4: {"seccion_idx": 0, "landmark": "carga"}}
            clearance = -0.6 + float(offset_map.get("0", 0))
            if clearance < 0:
                return extraer_issues_de_pressure_zones(
                    [{"risk_level": "overlap", "face_index": 4, "clearance_mm": round(clearance, 2)}],
                    mapeo=mapeo,
                )
            return []
        else:
            # offset_surface reteseló: ahora face_index=4 es la sección 3
            # (z=62mm) -- alta presión. Mismo face_index, sección distinta.
            mapeo = {4: {"seccion_idx": 3, "landmark": None}}
            espesor = 1.0 + float(offset_map.get("3", 0))
            if espesor < UMBRALES["espesor_min_objetivo_mm"]:
                return extraer_issues_de_pressure_zones(
                    [{"risk_level": "high_pressure", "face_index": 4, "clearance_mm": round(espesor, 2)}],
                    mapeo=mapeo,
                )
            return []

    parametros_iniciales = {"offset_map": {"0": 0.0, "3": 0.0}}
    resultado = ciclo_qa(parametros_iniciales, generar_fn=generar_fn, evaluar_fn=evaluar_fn)
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    print("parametros_finales:", json.dumps(resultado.parametros_finales, indent=2, ensure_ascii=False))
    for h in resultado.historial:
        print(f"\n-- iteración {h['iteracion']} ({h['estado']}) --")
        for iss in h["issues"]:
            print(f"   issue: {iss['tipo']} face_index={iss['face_index']} -> seccion={iss['seccion_idx']}  detalle={iss['detalle']}")
        for aj in h["ajustes"]:
            print(f"   ajuste: {aj['parametro']} delta={aj['delta_mm']:+}mm (face_index origen={aj['face_index']})")
    claves_finales = set(resultado.parametros_finales["offset_map"].keys())
    print(f"\nclaves finales en offset_map: {sorted(claves_finales)}  "
          f"(nunca debería aparecer '4' -- esa cara no es ninguna sección real)")


def _demo_caso_face_sin_mapeo():
    print("\n" + "=" * 70)
    print("DEMO 4: face_index sin mapeo (cara ambigua) -> escala, no adivina")
    print("=" * 70)

    def generar_fn(parametros):
        return {}

    def evaluar_fn(resultado_geometria):
        # face_index=8 no está en el mapeo (como la cara ambigua del
        # self-test de mapear_caras_a_secciones.py) -> seccion_idx=None
        return extraer_issues_de_pressure_zones(
            [{"risk_level": "high_pressure", "face_index": 8, "clearance_mm": 0.9}],
            mapeo={4: {"seccion_idx": 3, "landmark": None}},  # no incluye la cara 8
        )

    resultado = ciclo_qa({"offset_map": {}}, generar_fn, evaluar_fn)
    print(f"\naprobado={resultado.aprobado}  iteraciones={resultado.iteraciones}")
    for esc in resultado.escalamientos:
        print(f"ESCALAMIENTO: {esc.razon}")


if __name__ == "__main__":
    _demo_caso_convergente()
    _demo_caso_escala()
    _demo_caso_face_index_inestable()
    _demo_caso_face_sin_mapeo()
