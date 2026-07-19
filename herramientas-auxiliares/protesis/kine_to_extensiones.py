#!/usr/bin/env python3
"""
Extensiones de kinesiología y terapia ocupacional (kine/TO) al flujo de
diseño de socket protésico basado en munon_a_secciones.py.

Este módulo NO reemplaza a munon_a_secciones.py -- lo complementa con:

  1. trim_line          -> altura de corte proximal según rango articular
  2. familia de liners   -> volumen fluctuante (edema/atrofia), no solo
                            crecimiento pediátrico
  3. screening pistoning -> comparar contacto con carga vs sin carga
  4. tiempo de calce     -> señal de alarma si el donning/doffing es lento
                            (independencia funcional, dominio de TO)
  5. ventana de inspección de piel -> parámetros para un corte/cutout
                            (se ejecuta después con freecad:part_operations,
                            boolean cut, sobre el sólido ya generado)
  6. metadata de alineación y de dispositivo terminal / ADL
                            (información clínica que acompaña al modelo,
                            no geometría calculada por este script)

IMPORTANTE: todo esto es apoyo geométrico/organizativo para el proceso de
diseño. Ninguna salida de este script reemplaza el juicio clínico del
kinesiólogo, terapeuta ocupacional o protesista tratante, ni la prueba
física en el paciente.
"""
import json
import statistics


# ============================================================
# 1) TRIM LINE (línea de recorte proximal) -- KINESIOLOGÍA
# ============================================================
def definir_trim_line(landmark_referencia, offset_mm, posicion_mm_en_stack, direccion="proximal"):
    """
    landmark_referencia: ej. "hueco_popliteo", "pliegue_cubital", "axila",
               "maleolo", "talon"
    offset_mm: distancia desde el landmark hasta el borde del socket, en la
               MISMA convención que 'position' de cross_section_stack (0 =
               extremo proximal, crece hacia distal). El signo NO depende
               de 'direccion':
               Positivo = el borde queda MÁS DISTAL que el landmark.
               Negativo = el borde queda MÁS PROXIMAL que el landmark.
    posicion_mm_en_stack: a qué 'position' del cross_section_stack
               corresponde este landmark (0 = proximal).
    direccion: "proximal" (default) si landmark_referencia es un landmark
               proximal (hueco_popliteo, pliegue_cubital, axila) -> el
               socket no debe extenderse MÁS PROXIMAL que la trim line
               (se excluyen las secciones con position < altura_final_mm).
               "distal" si landmark_referencia es un landmark distal
               (maleolo, talon) -> el socket no debe extenderse MÁS DISTAL
               que la trim line (se excluyen las secciones con
               position > altura_final_mm).

    NOTA: confirmar siempre contra prueba física / criterio del
    kinesiólogo-TO tratante antes de aplicar al modelo final.
    """
    if direccion not in ("proximal", "distal"):
        raise ValueError(f"direccion debe ser 'proximal' o 'distal', recibido: {direccion!r}")

    return {
        "landmark_referencia": landmark_referencia,
        "offset_mm": offset_mm,
        "posicion_mm_en_stack": posicion_mm_en_stack,
        "direccion": direccion,
        "altura_final_mm": posicion_mm_en_stack + offset_mm,
    }


def advertir_secciones_sobre_trim_line(sections, trim_line):
    """Marca qué secciones de cross_section_stack quedarían fuera del
    socket final según la trim line definida y la dirección del landmark
    (ver definir_trim_line):

    direccion="proximal": sobran las secciones MÁS PROXIMALES que la trim
    line (position < altura_final_mm).
    direccion="distal": sobran las secciones MÁS DISTALES que la trim line
    (position > altura_final_mm)."""
    limite = trim_line["altura_final_mm"]
    direccion = trim_line.get("direccion", "proximal")

    if direccion == "proximal":
        sobrantes = [s for s in sections if s["position"] < limite]
        lado = "por encima (más proximal)"
    else:
        sobrantes = [s for s in sections if s["position"] > limite]
        lado = "por debajo (más distal)"

    if sobrantes:
        print(f"  [aviso] {len(sobrantes)} sección(es) quedan {lado} de la "
              f"trim line ({limite}mm) y deberían excluirse del socket final:")
        for s in sobrantes:
            print(f"    - position={s['position']}mm")
    return sobrantes


def familia_liners_por_volumen(perfil_base_sections, condiciones):
    """
    perfil_base_sections: el 'sections' generado por munon_a_secciones.py.
    condiciones: lista de dicts, ej.:
        [{"nombre": "manana_base", "offset_mm": 0},
         {"nombre": "tarde_con_edema", "offset_mm": 3},
         {"nombre": "post_actividad_intensa", "offset_mm": 5}]
    """
    offsets = [c["offset_mm"] for c in condiciones]
    nombres = [c["nombre"] for c in condiciones]

    print("  [nota] Reutilizando growth_socket_operations para volumen "
          "fluctuante (no crecimiento pediátrico). El shell exterior debe "
          "dimensionarse para la condición de MAYOR volumen (peor caso), "
          "y los liners más finos se usan cuando el muñón está más pequeño.")

    condiciones_por_offset = {}
    for offset, nombre in zip(offsets, nombres):
        if offset in condiciones_por_offset and condiciones_por_offset[offset] != nombre:
            raise ValueError(
                f"Offset {offset}mm ya está asignado a la condición "
                f"'{condiciones_por_offset[offset]}'; no se puede asignar también a "
                f"'{nombre}' -- dos condiciones con el mismo offset se pisan en "
                f"silencio si no se resuelve explícitamente."
            )
        condiciones_por_offset[offset] = nombre

    return {
        "operation_shell": "create_outer_shell",
        "operation_liners": "create_liner_family",
        "growth_offsets_mm": offsets,
        "condiciones_por_offset": condiciones_por_offset,
        "max_liner_offset_mm": max(offsets),
    }


# ============================================================
# 3) SCREENING DE PISTONING -- KINESIOLOGÍA
# ============================================================
def plan_screening_pistoning(socket_shape, limb_model_cargado, limb_model_descargado):
    """
    Plan de llamadas a freecad:contact_pressure_operations para aproximar
    el riesgo de pistoning. No calcula el resultado -- hay que correr las
    dos llamadas en FreeCAD y comparar manualmente.
    """
    return {
        "paso_1_cargado": {
            "operation": "sample_socket_clearance",
            "socket_shape": socket_shape,
            "limb_model_shape": limb_model_cargado,
        },
        "paso_2_descargado": {
            "operation": "sample_socket_clearance",
            "socket_shape": socket_shape,
            "limb_model_shape": limb_model_descargado,
        },
        "interpretacion": (
            "Si el área de contacto 'overlap' cae mucho entre cargado y "
            "descargado, o si aparecen huecos de 'no contacto' en la zona "
            "proximal en la condición descargada, es señal geométrica de "
            "riesgo de pistoning. Esto es un proxy, no un diagnóstico -- "
            "confirmar siempre con observación de la marcha del paciente."
        ),
    }


# ============================================================
# 4) TIEMPO DE CALCE (donning/doffing) -- TERAPIA OCUPACIONAL
# ============================================================
def evaluar_independencia_calce(historial_donning_time_sec, umbral_alerta_seg=120):
    """
    historial_donning_time_sec: lista de donning_time_sec de
        freecad:fitting_history_operations -> get_fitting_history,
        en orden cronológico.
    """
    if not historial_donning_time_sec:
        return {"alerta": False, "motivo": "sin datos de historial todavía"}

    promedio = statistics.mean(historial_donning_time_sec)
    tendencia = None
    if len(historial_donning_time_sec) >= 2:
        primera_mitad = historial_donning_time_sec[: len(historial_donning_time_sec) // 2]
        segunda_mitad = historial_donning_time_sec[len(historial_donning_time_sec) // 2:]
        tendencia = "mejorando" if statistics.mean(segunda_mitad) < statistics.mean(primera_mitad) else "empeorando_o_estable"

    alerta = promedio > umbral_alerta_seg
    return {
        "alerta": alerta,
        "promedio_seg": round(promedio, 1),
        "tendencia": tendencia,
        "sugerencia": (
            "Revisar geometría de la abertura/entrada del socket y "
            "considerar liner de calce asistido si el promedio no mejora "
            "en las próximas sesiones." if alerta else
            "Tiempo de calce dentro de rango razonable por ahora."
        ),
    }


# ============================================================
# 5) VENTANA DE INSPECCIÓN DE PIEL -- KINESIOLOGÍA / TO
# ============================================================
def definir_ventana_inspeccion(posicion_mm, ancho_mm, alto_mm, forma="rounded_rect"):
    return {
        "nota": (
            "Estos parámetros describen la ventana deseada. Para crearla: "
            "1) generar una caja/cilindro auxiliar con freecad:part_operations "
            "en esta posición y tamaño, 2) restarla del socket sólido con "
            "una operación boolean 'cut'. No es una operación directa de "
            "organic_operations."
        ),
        "posicion_mm": posicion_mm,
        "ancho_mm": ancho_mm,
        "alto_mm": alto_mm,
        "forma": forma,
        "recomendacion_clinica": (
            "Ubicar lejos de zonas de carga (landmark='carga') para no "
            "comprometer la rigidez estructural en el punto de apoyo."
        ),
    }


# ============================================================
# 6) METADATA CLÍNICA -- NO ES GEOMETRÍA, ES CONTEXTO
# ============================================================
PLANTILLA_ALINEACION = {
    "tipo_socket": None,
    "eje_referencia": None,
    "desplazamiento_medial_lateral_mm": None,
    "desplazamiento_ap_mm": None,
    "flexion_inicial_deg": None,
    "nota": (
        "La alineación protésica real se define y ajusta en el banco de "
        "alineación por el protesista/kinesiólogo con el paciente de pie "
        "y caminando. Estos campos son metadata de referencia para "
        "documentar la prescripción, no un cálculo geométrico de este "
        "sistema."
    ),
}

DISPOSITIVOS_TERMINALES_ADL = {
    "gancho_voluntario": {
        "actividades_favorecidas": ["agarre de precisión", "tareas con fuerza (herramientas)"],
        "limitaciones_TO": ["menor aceptación estética", "curva de aprendizaje motor"],
    },
    "mano_mioelectrica": {
        "actividades_favorecidas": ["prensión cilíndrica", "actividades bimanuales simétricas"],
        "limitaciones_TO": ["peso adicional", "mantenimiento/carga de batería"],
    },
    "pinza_pasiva_cosmetica": {
        "actividades_favorecidas": ["apoyo pasivo, sostener objetos livianos"],
        "limitaciones_TO": ["sin agarre activo, rol principalmente estético/funcional pasivo"],
    },
}


def main():
    print("Este módulo se usa importando sus funciones junto con "
          "munon_a_secciones.py -- no tiene un flujo único de línea de "
          "comandos porque cada pieza depende de datos clínicos distintos "
          "(trim line, condiciones de volumen, historial de calce, etc.). "
          "Ver los docstrings de cada función para el formato esperado.")

    ejemplo_trim = definir_trim_line("hueco_popliteo", offset_mm=-20, posicion_mm_en_stack=100)
    print("\nEjemplo trim_line:")
    print(json.dumps(ejemplo_trim, indent=2, ensure_ascii=False))

    ejemplo_liners = familia_liners_por_volumen(
        perfil_base_sections=[],
        condiciones=[
            {"nombre": "manana_base", "offset_mm": 0},
            {"nombre": "tarde_con_edema", "offset_mm": 3},
        ],
    )
    print("\nEjemplo familia de liners por volumen:")
    print(json.dumps(ejemplo_liners, indent=2, ensure_ascii=False))

    ejemplo_calce = evaluar_independencia_calce([180, 150, 130])
    print("\nEjemplo evaluación de independencia de calce:")
    print(json.dumps(ejemplo_calce, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
