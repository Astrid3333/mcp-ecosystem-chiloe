#!/usr/bin/env python3
"""
Convierte medidas manuales de muñón (circunferencia + AP/ML con calibre)
al formato 'sections' que espera freecad:organic_operations (cross_section_stack).

Uso típico:
    1. Tomar medidas en el paciente a distintas alturas (ver protocolo abajo).
    2. Completar la lista MEDICIONES.
    3. Correr este script -> imprime el array 'sections' listo para pasar
       directo al parámetro 'sections' de organic_operations/cross_section_stack.

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


def construir_secciones(mediciones, wall_thickness_map=True):
    sections = []
    offset_map = {}

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

        sections.append({
            "position": m["position_mm"],
            "shape": "ellipse",
            "width": ap,   # antero-posterior
            "height": ml,  # medio-lateral
        })

        landmark = m.get("landmark")
        if landmark == "carga":
            offset_map[i] = ESPESOR_CARGA
        elif landmark == "alivio":
            offset_map[i] = ESPESOR_ALIVIO
        else:
            offset_map[i] = ESPESOR_NORMAL

    return sections, offset_map


def main():
    sections, offset_map = construir_secciones(MEDICIONES)

    print("\n" + "=" * 60)
    print("Parámetros listos para freecad:organic_operations")
    print("=" * 60)

    print("\n--- Paso 1: cross_section_stack ---")
    print("operation = 'cross_section_stack'")
    print("sections =")
    print(json.dumps(sections, indent=2, ensure_ascii=False))

    print("\n--- Paso 2: offset_surface (espesor variable por zona) ---")
    print("operation = 'offset_surface'")
    print("offset_map = (índice de sección -> espesor mm)")
    print(json.dumps(offset_map, indent=2, ensure_ascii=False))
    print("\nNota: offset_map en la tool usa 'face_index' como clave;")
    print("verificar en FreeCAD cómo quedan numeradas las caras tras el")
    print("cross_section_stack antes de aplicar el offset, puede no ser 1:1")
    print("con el índice de sección de medición.")

    print("\n--- Paso 3 sugerido ---")
    print("Correr freecad:contact_pressure_operations -> sample_socket_clearance")
    print("contra un modelo del muñón (este mismo cross_section_stack sin el")
    print("offset, como proxy del muñón real) para screening geométrico previo")
    print("a la prueba física.")


if __name__ == "__main__":
    main()
