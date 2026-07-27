#!/usr/bin/env python3
"""
Convierte medidas manuales de muñón (circunferencia + AP/ML con calibre)
al formato 'sections' que espera freecad:organic_operations (cross_section_stack).

ARQUITECTURA (revisión 2026-07-27): el espesor de pared YA NO se aplica con
offset_surface + offset_map por face_index. Un loft suave (spline, la única
forma de conseguir curvatura anatómica real en cross_section_stack) genera
una sola cara lateral continua en OCC -- no hay "cara de la sección N" que
clasificar, así que cualquier offset por face_index es inherentemente frágil
(en el mejor caso) o directamente inaplicable (en el peor).

En vez de eso: el espesor se hornea en el PERFIL de cada sección. Se generan
dos stacks de secciones -- outer (medidas reales del muñón) e inner (mismas
medidas, contraídas localmente por el espesor que corresponda a ese
landmark) -- se loftean por separado y se restan con un booleano. El mapeo
landmark -> espesor pasa a ser una decisión que se toma ANTES de tocar
FreeCAD, sobre datos que vos ya conocés con certeza (tus propias mediciones),
en vez de una que se intenta reconstruir DESPUÉS sobre topología ambigua.

mapear_caras_a_secciones.py sigue siendo útil, pero solo para el rol que sí
puede cumplir de forma confiable: etiquetar con landmark las zonas que
devuelve contact_pressure_operations/summarize_pressure_zones para el
reporte de QA -- no para decidir dónde va más o menos espesor durante la
construcción.

Uso típico:
    1. Tomar medidas en el paciente a distintas alturas (ver protocolo abajo).
    2. Completar la lista MEDICIONES.
    3. Correr este script -> imprime los dos arrays 'sections' (outer e
       inner) y los pasos de FreeCAD para loftear ambos y restarlos.

PROTOCOLO DE MEDICIÓN SUGERIDO (ejemplo trans-tibial, adaptar a nivel real):
    - Medir cada 20mm desde el punto más proximal hasta el extremo distal.
    - En cada altura tomar:
        circunferencia_mm: con cinta métrica, vuelta completa.
        ap_mm: diámetro antero-posterior con calibre (de adelante hacia atrás).
        ml_mm: diámetro medio-lateral con calibre (de lado a lado).
      Si solo se puede tomar UNA medida además de la circunferencia, priorizar AP
      (suele ser la dimensión más variable en trans-tibial).
    - Marcar explícitamente las alturas que correspondan a:
        landmark="carga"  -> zona de apoyo de carga (ej. tendón rotuliano):
                              necesita MÁS espesor de pared (más rígido).
        landmark="alivio" -> prominencia ósea (ej. cabeza del peroné, cresta
                              tibial, extremo distal tibia): necesita MENOS
                              espesor de pared / cámara de alivio.
        landmark=None     -> zona de transición normal.

IMPORTANTE: esto es un ayudante geométrico, no un dispositivo médico validado.
El ajuste final siempre debe confirmarse con prueba física en el paciente y,
si corresponde, con freecad:contact_pressure_operations como screening previo.
"""
import json
import math

# ------------------------------------------------------------------
# 1) COMPLETAR CON LAS MEDIDAS REALES DEL PACIENTE
#    position_mm: distancia desde el punto más proximal (0) hacia distal.
#    circunferencia_mm: opcional si ya se tienen ap_mm y ml_mm.
#    ap_mm / ml_mm: diámetros con calibre (recomendado).
#    landmark: "carga", "alivio", o None.
# ------------------------------------------------------------------
MEDICIONES = [
    {"position_mm": 0,   "ap_mm": 90, "ml_mm": 78, "landmark": "carga"},   # ejemplo: zona proximal, tendón rotuliano
    {"position_mm": 20,  "ap_mm": 85, "ml_mm": 76, "landmark": None},
    {"position_mm": 40,  "ap_mm": 78, "ml_mm": 70, "landmark": "alivio"},  # ejemplo: cabeza del peroné
    {"position_mm": 60,  "ap_mm": 72, "ml_mm": 65, "landmark": None},
    {"position_mm": 80,  "ap_mm": 66, "ml_mm": 60, "landmark": None},
    {"position_mm": 100, "ap_mm": 58, "ml_mm": 52, "landmark": "alivio"},  # ejemplo: extremo distal tibia
]

# Espesores de pared (mm) según tipo de zona -- ajustar según material e impresora.
ESPESOR_CARGA = 4.0     # más rígido, soporta peso
ESPESOR_NORMAL = 3.0
ESPESOR_ALIVIO = 2.0    # más flexible / cámara de alivio


def circunferencia_a_diametro_elipse(circunferencia_mm, relacion_ap_ml=1.15):
    """
    Fallback SOLO si no hay AP/ML medidos con calibre, solo circunferencia
    con cinta. Asume una relación AP:ML típica (el muñón suele ser un poco
    más ancho antero-posterior que medio-lateral; 1.15 es un valor de partida
    razonable pero ARBITRARIO -- siempre preferir calibre real si es posible).

    Usa la aproximación de Ramanujan para el perímetro de una elipse,
    resuelta numéricamente para (a, b) dado el perímetro y la relación a/b.
    """
    # b = ml/2, a = ap/2 = b * relacion_ap_ml
    # Ramanujan: P ≈ π[3(a+b) - sqrt((3a+b)(a+3b))]
    def perimetro(b):
        a = b * relacion_ap_ml
        return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))

    lo, hi = 1.0, circunferencia_mm
    for _ in range(60):
        mid = (lo + hi) / 2
        if perimetro(mid) < circunferencia_mm:
            lo = mid
        else:
            hi = mid
    b = (lo + hi) / 2
    a = b * relacion_ap_ml
    return round(2 * a, 1), round(2 * b, 1)  # ap_mm, ml_mm


ESPESOR_MINIMO_MM = 1.2  # piso de seguridad: por debajo de esto el inner casi
                          # toca el outer y el cut puede degenerar (pared
                          # infinitamente fina o cara inválida). Si una sección
                          # necesita menos que esto, construir_secciones() la
                          # deja pasar pero avisa fuerte -- no la sube en silencio.


def _espesor_para_landmark(landmark):
    if landmark == "carga":
        return ESPESOR_CARGA
    elif landmark == "alivio":
        return ESPESOR_ALIVIO
    else:
        return ESPESOR_NORMAL


def construir_secciones(mediciones):
    """
    Devuelve (sections_outer, sections_inner, espesor_map):
      sections_outer:  perfil real del muñón, para el loft exterior.
      sections_inner:  mismo perfil, contraído localmente según el espesor
                        de esa sección -- para el loft interior. width/height
                        se reducen 2x el espesor (una vez por lado).
      espesor_map:      {seccion_idx: espesor_mm} -- se devuelve también por
                        separado porque sirve como referencia al pasarle las
                        MEDICIONES originales a
                        mapear_caras_a_secciones.posiciones_referencia_desde_mediciones()
                        para el etiquetado de QA (ver docstring del módulo).
    """
    sections_outer = []
    sections_inner = []
    espesor_map = {}

    for i, m in enumerate(mediciones):
        ap = m.get("ap_mm")
        ml = m.get("ml_mm")

        if ap is None or ml is None:
            if "circunferencia_mm" not in m:
                raise ValueError(
                    f"Sección en position_mm={m['position_mm']}: falta ap_mm/ml_mm "
                    f"o circunferencia_mm. No se puede adivinar la forma sin datos."
                )
            ap, ml = circunferencia_a_diametro_elipse(m["circunferencia_mm"])
            print(f"  [aviso] position_mm={m['position_mm']}: solo había circunferencia, "
                  f"se estimó ap={ap}mm ml={ml}mm asumiendo elipse típica. "
                  f"Preferible remedir con calibre.")

        landmark = m.get("landmark")
        espesor = _espesor_para_landmark(landmark)
        espesor_map[i] = espesor

        ap_inner = ap - 2 * espesor
        ml_inner = ml - 2 * espesor

        if ap_inner < ESPESOR_MINIMO_MM or ml_inner < ESPESOR_MINIMO_MM:
            raise ValueError(
                f"Sección en position_mm={m['position_mm']} (landmark={landmark!r}, "
                f"espesor={espesor}mm): el perfil interior queda en "
                f"ap={ap_inner:.1f}mm / ml={ml_inner:.1f}mm, por debajo del piso de "
                f"seguridad ({ESPESOR_MINIMO_MM}mm). El muñón es demasiado angosto en "
                f"esta altura para ese espesor -- bajar ESPESOR_* para esta zona o "
                f"remedir, no se genera geometría inválida en silencio."
            )

        sections_outer.append({
            "position": m["position_mm"],
            "shape": "ellipse",
            "width": ap,     # antero-posterior
            "height": ml,    # medio-lateral
        })
        sections_inner.append({
            "position": m["position_mm"],
            "shape": "ellipse",
            "width": ap_inner,
            "height": ml_inner,
        })

    return sections_outer, sections_inner, espesor_map


def main():
    sections_outer, sections_inner, espesor_map = construir_secciones(MEDICIONES)

    print("\n" + "=" * 60)
    print("Parámetros listos para freecad:organic_operations")
    print("=" * 60)

    print("\n--- Paso 1: loft exterior (cross_section_stack) ---")
    print("operation = 'cross_section_stack'")
    print("name = 'Socket_Outer'")
    print("sections =")
    print(json.dumps(sections_outer, indent=2, ensure_ascii=False))

    print("\n--- Paso 2: loft interior (cross_section_stack) ---")
    print("El espesor de cada sección ya está horneado en estos perfiles")
    print("(width/height = perfil real - 2x espesor de esa zona), así que")
    print("este loft NO necesita ningún offset después.")
    print("operation = 'cross_section_stack'")
    print("name = 'Socket_Inner'")
    print("sections =")
    print(json.dumps(sections_inner, indent=2, ensure_ascii=False))

    print("\n--- Paso 3: restar (freecad:boolean_operations -> cut_objects) ---")
    print("operation = 'cut_objects'")
    print("base = 'Socket_Outer'")
    print("tools = ['Socket_Inner']")
    print("name = 'Socket_Wall'")
    print("\nEspesor efectivo por sección (referencia, ya aplicado arriba):")
    print(json.dumps(espesor_map, indent=2, ensure_ascii=False))

    print("\n--- Paso 4 sugerido: QA ---")
    print("Correr freecad:contact_pressure_operations -> sample_socket_clearance")
    print("de 'Socket_Wall' contra un modelo del muñón (el loft de")
    print("sections_outer, sin el corte, como proxy del muñón real).")
    print("Para etiquetar las zonas resultantes con landmark en vez de solo")
    print("face_index, usar mapear_caras_a_secciones.py:")
    print("  posiciones_ref = posiciones_referencia_desde_mediciones(MEDICIONES)")
    print("  mapeo, ambiguas = clasificar_caras(caras_de_socket_wall, posiciones_ref)")
    print("  zonas_con_landmark = enriquecer_zonas_con_landmark(zonas_qa, mapeo)")
    print("(ahí sí tiene sentido: Socket_Wall, post-corte, puede volver a tener")
    print("caras discretas que clasificar -- ya no es un loft C1 continuo puro.")
    print("Igual sigue devolviendo ambiguas en vez de adivinar, como siempre.)")


if __name__ == "__main__":
    main()
