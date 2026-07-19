"""
Genera el contorno (lista de puntos x,y) de una sección elíptica modulada
por offsets radiales en las 4 direcciones cardinales (anterior/posterior/
medial/lateral), interpolando suavemente entre ellas para evitar el
escalón que tendría un corte por cuadrante sin interpolar.

Sin dependencia de FreeCAD -- es la parte de este trabajo que se puede
testear fuera de un entorno con FreeCAD/Part instalado. La conversión a
Part.Wire (organic_ops.py, _polygon_wire) se agrega después, en el
entorno de Astrid, porque requiere FreeCAD.

La interpolación entre cardinales es lineal por tramos (ver
_offset_en_angulo) -- exacta en los 4 puntos, continua, con un quiebre
suave (no un salto) en cada cardinal.

CONVENCIÓN ANGULAR (LOCAL a esta función, TODAVÍA NO CONFIRMADA contra la
convención real de ejes/twist_deg de cross_section_stack en el pipeline
de Astrid -- confirmar antes de usar para generar geometría real, para no
repetir el error de convención cruzada que ya pasó una vez con 'position'):
    0°   = anterior  (a lo largo de +X local)
    90°  = lateral
    180° = posterior
    270° = medial
    ángulo crece counter-clockwise visto desde +Z.
"""
import math

_CARDINALES = {"anterior": 0.0, "lateral": 90.0, "posterior": 180.0, "medial": 270.0}


_ORDEN_CARDINALES = ["anterior", "lateral", "posterior", "medial"]  # 0, 90, 180, 270


def _offset_en_angulo(theta_deg, offsets_mm_por_cuadrante):
    """Interpola linealmente entre los dos cardinales adyacentes a theta_deg.

    Nota de diseño: se probó primero un blend ponderado tipo 'raised
    cosine' entre los 4 cardinales, pero esa aproximación NUNCA da el
    offset exacto pedido en el propio cardinal -- los vecinos siempre
    diluyen un poco el resultado (ej. offsets_mm_por_cuadrante={"posterior":
    -15} daba ~-13.3 en theta=180°, no -15). La interpolación lineal por
    tramos entre los 2 cardinales adyacentes es más simple y SÍ es exacta
    en los 4 puntos por construcción; el costo es que la derivada no es
    continua justo en cada cardinal (hay un 'quiebre' suave, no un salto),
    lo cual sigue siendo aceptable para una función de aviso/guía."""
    theta_deg = theta_deg % 360
    i = int(theta_deg // 90) % 4
    j = (i + 1) % 4
    frac = (theta_deg % 90) / 90.0
    nombre_i, nombre_j = _ORDEN_CARDINALES[i], _ORDEN_CARDINALES[j]
    offset_i = offsets_mm_por_cuadrante.get(nombre_i, 0.0)
    offset_j = offsets_mm_por_cuadrante.get(nombre_j, 0.0)
    return offset_i * (1 - frac) + offset_j * frac


def perfil_seccion_asimetrica(width, height, offsets_mm_por_cuadrante, n_puntos=72):
    """
    width, height: diámetros AP/ML de la elipse base (mm), mismo significado
        que 'width'/'height' en las secciones de cross_section_stack.
    offsets_mm_por_cuadrante: dict con claves entre "anterior", "posterior",
        "medial", "lateral" (subconjunto válido; las que falten valen 0 =
        sin cambio respecto a la elipse base). Valor = mm a SUMAR al radio
        local en esa dirección (positivo = el borde se aleja del centro,
        negativo = se acerca).
    n_puntos: cantidad de puntos muestreados alrededor de la elipse (más
        puntos = interpolación más suave entre offsets cardinales, a costo
        de geometría más pesada).

    Devuelve lista de (x, y) puntos que cierran el contorno (mismo formato
    que espera _polygon_wire en organic_ops.py).
    """
    if width <= 0 or height <= 0:
        raise ValueError("width y height deben ser > 0")
    if n_puntos < 8:
        raise ValueError("n_puntos debe ser >= 8 para una interpolación razonable")

    claves_invalidas = set(offsets_mm_por_cuadrante) - set(_CARDINALES)
    if claves_invalidas:
        raise ValueError(
            f"offsets_mm_por_cuadrante tiene claves inválidas: {claves_invalidas!r}; "
            f"válidas: {sorted(_CARDINALES)}"
        )

    a, b = width / 2.0, height / 2.0
    puntos = []
    for i in range(n_puntos):
        theta = 360.0 * i / n_puntos
        rad = math.radians(theta)
        x_base, y_base = a * math.cos(rad), b * math.sin(rad)
        r_base = math.hypot(x_base, y_base)
        if r_base < 1e-9:
            puntos.append((0.0, 0.0))
            continue
        ux, uy = x_base / r_base, y_base / r_base
        r_final = r_base + _offset_en_angulo(theta, offsets_mm_por_cuadrante)
        if r_final <= 0:
            raise ValueError(
                f"El offset en theta={theta:.1f}° deja un radio <= 0 "
                f"({r_final:.2f}mm) -- offset demasiado negativo para esta "
                f"geometría base (width={width}, height={height})."
            )
        puntos.append((ux * r_final, uy * r_final))
    return puntos
