"""
Tests para kine_to_extensiones.py.

Fija los casos verificados manualmente durante el desarrollo (proximal,
distal, dirección inválida, colisión/no-colisión de liners) para que una
regresión futura se note al tiro en vez de en producción con datos reales.
"""
import pytest

from kine_to_extensiones import (
    definir_trim_line,
    advertir_secciones_sobre_trim_line,
    familia_liners_por_volumen,
)


# ------------------------------------------------------------------
# definir_trim_line
# ------------------------------------------------------------------
def test_trim_line_proximal_default():
    tl = definir_trim_line("hueco_popliteo", offset_mm=15, posicion_mm_en_stack=0)
    assert tl["direccion"] == "proximal"
    assert tl["altura_final_mm"] == 15


def test_trim_line_distal_explicito():
    tl = definir_trim_line("maleolo", offset_mm=-10, posicion_mm_en_stack=180, direccion="distal")
    assert tl["direccion"] == "distal"
    assert tl["altura_final_mm"] == 170


def test_trim_line_direccion_invalida_levanta_error():
    with pytest.raises(ValueError):
        definir_trim_line("x", 0, 0, direccion="lateral")


# ------------------------------------------------------------------
# advertir_secciones_sobre_trim_line
# ------------------------------------------------------------------
@pytest.fixture
def sections_20mm():
    return [{"position": p} for p in range(0, 201, 20)]


def test_advertir_proximal(sections_20mm):
    tl = definir_trim_line("hueco_popliteo", offset_mm=15, posicion_mm_en_stack=0)
    sobrantes = advertir_secciones_sobre_trim_line(sections_20mm, tl)
    assert sobrantes == [{"position": 0}]


def test_advertir_distal(sections_20mm):
    tl = definir_trim_line("maleolo", offset_mm=-10, posicion_mm_en_stack=180, direccion="distal")
    sobrantes = advertir_secciones_sobre_trim_line(sections_20mm, tl)
    assert sobrantes == [{"position": 180}, {"position": 200}]


def test_advertir_sin_sobrantes(sections_20mm):
    # trim line que no excluye ninguna sección del stack
    tl = definir_trim_line("hueco_popliteo", offset_mm=-1, posicion_mm_en_stack=0)
    sobrantes = advertir_secciones_sobre_trim_line(sections_20mm, tl)
    assert sobrantes == []


# ------------------------------------------------------------------
# familia_liners_por_volumen
# ------------------------------------------------------------------
def test_familia_liners_basico_sin_colision():
    resultado = familia_liners_por_volumen(
        perfil_base_sections=[],
        condiciones=[
            {"nombre": "manana_base", "offset_mm": 0},
            {"nombre": "tarde_con_edema", "offset_mm": 3},
            {"nombre": "post_actividad_intensa", "offset_mm": 5},
        ],
    )
    assert resultado["growth_offsets_mm"] == [0, 3, 5]
    assert resultado["max_liner_offset_mm"] == 5
    assert resultado["condiciones_por_offset"][3] == "tarde_con_edema"


def test_familia_liners_colision_exacta_levanta_error():
    with pytest.raises(ValueError):
        familia_liners_por_volumen(
            perfil_base_sections=[],
            condiciones=[
                {"nombre": "manana_base", "offset_mm": 3},
                {"nombre": "otra_condicion", "offset_mm": 3},
            ],
        )


def test_familia_liners_colision_por_tolerancia_levanta_error():
    # Offsets casi idénticos (diferencia de una fracción insignificante de mm),
    # como podrían salir de un cálculo en vez de ser constantes escritas a mano.
    with pytest.raises(ValueError):
        familia_liners_por_volumen(
            perfil_base_sections=[],
            condiciones=[
                {"nombre": "manana_base", "offset_mm": 3.0},
                {"nombre": "otra_condicion", "offset_mm": 3.0000001},
            ],
        )


def test_familia_liners_offsets_distintos_no_colisionan():
    # Diferencia real (no solo error de punto flotante) no debe levantar error.
    resultado = familia_liners_por_volumen(
        perfil_base_sections=[],
        condiciones=[
            {"nombre": "manana_base", "offset_mm": 0},
            {"nombre": "tarde_con_edema", "offset_mm": 2.5},
        ],
    )
    assert resultado["max_liner_offset_mm"] == 2.5
