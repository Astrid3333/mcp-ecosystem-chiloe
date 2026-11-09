#!/usr/bin/env python3
"""
btfloat: punto flotante en ternario balanceado, construido sobre ternary.integer.Int (btern)

Representa un numero como  valor = int(mantissa) * 3**exponent
donde 'mantissa' es un Int (btern) de ancho fijo en trits, y 'exponent' un
entero Python normal (base 3, no base 2 como en IEEE 754).

Propiedad clave que se explota aqui: en ternario balanceado, TRUNCAR
(descartar los trits menos significativos) es matematicamente equivalente a
REDONDEAR al valor representable mas cercano. Esto es porque el rango de
valores que puede tomar la porcion descartada es simetrico alrededor de
cero (-0.5..+0.5 de la unidad del ultimo trit conservado), a diferencia de
binario/decimal donde truncar sesga sistematicamente el error en una
direccion. No hace falta logica de redondeo explicita: el truncamiento ya
es correcto por construccion.

NOTA sobre los dos sanity checks de mas abajo (revision 2026-07-27):
  - bias_truncamiento(): mide lo que la claim de arriba realmente predice
    -- la DIRECCION del error de redondeo sobre muchas muestras aleatorias
    independientes. Es el test que confirma o refuta el docstring.
  - comparacion_mapa_logistico(): NO mide sesgo, mide MAGNITUD de error
    acumulado sobre una sola trayectoria caotica (r=3.99), con precision
    desigual entre los dos sistemas (width=24 trits equivalen a ~15.1 bits
    de mantisa -- log2(3**24) -- muy por debajo de los 52 bits de float64,
    asi que no es un test de precision comparable). Cualquier sistema
    caotico amplifica exponencialmente diferencias de precision con cada
    iteracion; que btfloat24 acumule mas error de magnitud ahi no dice
    nada sobre si tiene o no sesgo. Se deja como ejemplo de sensibilidad
    caotica a la precision, no como evidencia a favor o en contra de
    btfloat.
"""

import math
from ternary.integer import Int


class BTFloat:
    __slots__ = ("mantissa", "exponent", "width")

    def __init__(self, mantissa, exponent, width=24):
        if not isinstance(mantissa, Int):
            mantissa = Int(mantissa)
        self.mantissa = mantissa
        self.exponent = exponent
        self.width = width
        self._normalize(width)

    def _normalize(self, width):
        trits = list(self.mantissa.trits)
        # quitar ceros a la izquierda (btern ya provee trim, pero por si acaso)
        while len(trits) > 1 and trits[0].value == 0:
            trits.pop(0)
        if len(trits) > width:
            drop = len(trits) - width
            trits = trits[:width]  # descarta los 'drop' trits menos significativos
            self.exponent += drop
            self.mantissa = Int(trits)
        else:
            self.mantissa = Int(trits)

    @classmethod
    def from_float(cls, x, width=24):
        if x == 0:
            return cls(Int(0), 0, width)
        e = math.floor(math.log(abs(x), 3)) - width + 1
        scaled = round(x / (3.0 ** e))
        return cls(Int(int(scaled)), e, width)

    def to_float(self):
        return float(int(self.mantissa)) * (3.0 ** self.exponent)

    def _align(self, other):
        """Escala ambas mantisas a un exponente comun (el menor de los dos)."""
        e = min(self.exponent, other.exponent)
        ma = Int(int(self.mantissa) * (3 ** (self.exponent - e)))
        mb = Int(int(other.mantissa) * (3 ** (other.exponent - e)))
        return ma, mb, e

    def __add__(self, other):
        ma, mb, e = self._align(other)
        return BTFloat(ma + mb, e, width=max(self.width, other.width))

    def __sub__(self, other):
        ma, mb, e = self._align(other)
        return BTFloat(ma - mb, e, width=max(self.width, other.width))

    def __mul__(self, other):
        return BTFloat(self.mantissa * other.mantissa, self.exponent + other.exponent,
                        width=max(self.width, other.width))

    def __repr__(self):
        return f"BTFloat({self.to_float():.10g}, mantissa={self.mantissa!r}, exp={self.exponent})"


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def bias_truncamiento(n_muestras=10000, width=24, seed=42):
    """Compara la DIRECCION del error de truncar en btern contra cero, sobre
    muchos valores aleatorios independientes -- no la magnitud sobre una
    sola trayectoria caotica. Si el truncamiento en ternario balanceado no
    tiene sesgo direccional, la media del error debe quedar muy por debajo
    del error absoluto medio (idealmente ordenes de magnitud menor); si
    hubiera sesgo sistematico, ambos numeros se acercarian entre si.

    Devuelve (media_error, error_absoluto_medio, errores).
    """
    import random  # nosec: simulación numérica de errores, no criptografía
    random.seed(seed)
    errores = []
    for _ in range(n_muestras):
        x = random.uniform(-1000, 1000)  # nosec: valor de prueba, no clave criptográfica
        bt = BTFloat.from_float(x, width)
        errores.append(bt.to_float() - x)
    media = sum(errores) / len(errores)
    error_abs_medio = sum(abs(e) for e in errores) / len(errores)
    return media, error_abs_medio, errores


def comparacion_mapa_logistico(x0=0.4, r=3.99, n=40, width=24):
    """Acumulacion de error de magnitud sobre el mapa logistico (caotico,
    r=3.99) para btfloat24 vs float64, contra una referencia de alta
    precision con Decimal. Ver nota en el docstring del modulo: esto NO es
    un test de sesgo, es un ejemplo de como un sistema caotico amplifica
    cualquier diferencia de precision -- y width=24 trits (~15.1 bits) es
    bastante menos preciso que los 52 bits de mantisa de float64, asi que
    la comparacion de magnitudes no es sobre igual precision.
    """
    from decimal import Decimal, getcontext
    getcontext().prec = 50

    def logistic_decimal(x0, r, n):
        x = Decimal(x0)
        r = Decimal(r)
        traj = [x]
        for _ in range(n):
            x = r * x * (1 - x)
            traj.append(x)
        return traj

    def logistic_float64(x0, r, n):
        x = x0
        traj = [x]
        for _ in range(n):
            x = r * x * (1 - x)
            traj.append(x)
        return traj

    def logistic_btfloat(x0, r, n, width):
        x = BTFloat.from_float(x0, width)
        r_bt = BTFloat.from_float(r, width)
        one = BTFloat.from_float(1.0, width)
        traj = [x.to_float()]
        for _ in range(n):
            x = r_bt * x * (one - x)
            traj.append(x.to_float())
        return traj

    ref = logistic_decimal(x0, r, n)
    f64 = logistic_float64(x0, r, n)
    bt = logistic_btfloat(x0, r, n, width)
    return ref, f64, bt


if __name__ == "__main__":
    # --- sanity check 1: aritmetica basica ---
    a = BTFloat.from_float(3.14159265)
    b = BTFloat.from_float(2.71828183)
    print("a =", a.to_float(), "(objetivo 3.14159265)")
    print("b =", b.to_float(), "(objetivo 2.71828183)")
    print("a+b =", (a + b).to_float(), "(objetivo 5.85987448)")
    print("a*b =", (a * b).to_float(), "(objetivo 8.53973422)")
    print()

    # --- sanity check 2: sesgo de truncamiento (el test que importa) ---
    print("=" * 70)
    print("BIAS DE TRUNCAMIENTO (10000 muestras aleatorias, width=24)")
    print("=" * 70)
    media, error_abs_medio, _ = bias_truncamiento()
    print(f"media del error:        {media:.6e}")
    print(f"error absoluto medio:   {error_abs_medio:.6e}")
    print(f"razon (media/abs_medio): {abs(media) / error_abs_medio:.4f}  "
          f"(cerca de 0 => sin sesgo direccional; cerca de 1 => sesgo sistematico)")
    print()

    # --- sanity check 3: mapa logistico (magnitud, NO sesgo -- ver nota arriba) ---
    print("=" * 70)
    print("MAPA LOGISTICO r=3.99 -- magnitud de error acumulado (NO es test de sesgo)")
    print("=" * 70)
    from decimal import Decimal
    x0, r, n = 0.4, 3.99, 40
    ref, f64, bt = comparacion_mapa_logistico(x0, r, n)
    print(f"{'n':>3} {'float64 err':>16} {'btfloat24 err':>16}")
    for i in range(0, n + 1, 5):
        err_f64 = float(Decimal(f64[i]) - ref[i])
        err_bt = float(Decimal(bt[i]) - ref[i])
        print(f"{i:>3} {err_f64:>16.6e} {err_bt:>16.6e}")
