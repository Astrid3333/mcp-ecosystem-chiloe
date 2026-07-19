import math
import pytest

from perfil_seccion_asimetrica import perfil_seccion_asimetrica


def _punto_en_angulo(puntos, n_puntos, angulo_deg):
    idx = round(angulo_deg / 360.0 * n_puntos) % n_puntos
    return puntos[idx]


def test_sin_offsets_reproduce_elipse_base():
    width, height = 90, 78
    n = 72
    puntos = perfil_seccion_asimetrica(width, height, {}, n_puntos=n)
    # en anterior (theta=0) el radio debe ser ~width/2
    x0, y0 = _punto_en_angulo(puntos, n, 0)
    assert math.hypot(x0, y0) == pytest.approx(width / 2, abs=0.5)
    # en lateral (theta=90) el radio debe ser ~height/2
    x90, y90 = _punto_en_angulo(puntos, n, 90)
    assert math.hypot(x90, y90) == pytest.approx(height / 2, abs=0.5)


def test_offset_posterior_negativo_acorta_esa_zona():
    width, height = 90, 78
    n = 72
    puntos = perfil_seccion_asimetrica(
        width, height, {"posterior": -15}, n_puntos=n
    )
    x180, y180 = _punto_en_angulo(puntos, n, 180)
    radio_posterior = math.hypot(x180, y180)
    # la interpolación es exacta en los cardinales: offset -15 en un radio
    # base de width/2=45 debe dar exactamente 30, no una versión diluida
    assert radio_posterior == pytest.approx(45 - 15, abs=0.1)

    # en anterior (opuesto) no debería verse afectado por el offset posterior
    x0, y0 = _punto_en_angulo(puntos, n, 0)
    assert math.hypot(x0, y0) == pytest.approx(45, abs=0.1)


def test_offsets_son_exactos_en_los_4_cardinales():
    width, height = 90, 78
    n = 72
    offsets = {"anterior": 5, "lateral": -3, "posterior": -15, "medial": 2}
    puntos = perfil_seccion_asimetrica(width, height, offsets, n_puntos=n)

    esperado = {
        "anterior": (width / 2) + offsets["anterior"],
        "lateral": (height / 2) + offsets["lateral"],
        "posterior": (width / 2) + offsets["posterior"],
        "medial": (height / 2) + offsets["medial"],
    }
    for nombre, angulo in [("anterior", 0), ("lateral", 90),
                           ("posterior", 180), ("medial", 270)]:
        x, y = _punto_en_angulo(puntos, n, angulo)
        assert math.hypot(x, y) == pytest.approx(esperado[nombre], abs=0.1)


def test_transicion_suave_sin_escalon():
    # Entre dos cardinales con offsets distintos, el offset intermedio debe
    # variar monótonamente (sin saltos bruscos de un punto al siguiente).
    width, height = 90, 78
    n = 72
    puntos = perfil_seccion_asimetrica(
        width, height, {"anterior": 0, "posterior": -15}, n_puntos=n
    )
    radios = [math.hypot(x, y) for x, y in puntos]
    saltos = [abs(radios[i + 1] - radios[i]) for i in range(len(radios) - 1)]
    # ningún salto entre puntos consecutivos debería ser mayor a una
    # fracción pequeña del offset total (acá: menos de 2mm entre puntos
    # contiguos, con 72 puntos alrededor de 360°)
    assert max(saltos) < 2.0


def test_offset_excesivamente_negativo_levanta_error():
    with pytest.raises(ValueError):
        perfil_seccion_asimetrica(90, 78, {"posterior": -200}, n_puntos=72)


def test_clave_invalida_levanta_error():
    with pytest.raises(ValueError):
        perfil_seccion_asimetrica(90, 78, {"arriba": 5}, n_puntos=72)


def test_n_puntos_insuficiente_levanta_error():
    with pytest.raises(ValueError):
        perfil_seccion_asimetrica(90, 78, {}, n_puntos=4)
