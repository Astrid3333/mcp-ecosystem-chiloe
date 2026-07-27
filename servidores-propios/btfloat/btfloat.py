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


if __name__ == "__main__":
    # --- sanity check: aritmetica basica ---
    a = BTFloat.from_float(3.14159265)
    b = BTFloat.from_float(2.71828183)
    print("a =", a.to_float(), "(objetivo 3.14159265)")
    print("b =", b.to_float(), "(objetivo 2.71828183)")
    print("a+b =", (a + b).to_float(), "(objetivo 5.85987448)")
    print("a*b =", (a * b).to_float(), "(objetivo 8.53973422)")
    print()

    # --- comparacion de sesgo de truncamiento: mapa logistico r=3.99 ---
    # Referencia de alta precision con Python 'decimal' (50 digitos)
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

    def logistic_btfloat(x0, r, n, width=24):
        x = BTFloat.from_float(x0, width)
        r_bt = BTFloat.from_float(r, width)
        one = BTFloat.from_float(1.0, width)
        traj = [x.to_float()]
        for _ in range(n):
            x = r_bt * x * (one - x)
            traj.append(x.to_float())
        return traj

    x0, r, n = 0.4, 3.99, 40
    ref = logistic_decimal(x0, r, n)
    f64 = logistic_float64(x0, r, n)
    bt = logistic_btfloat(x0, r, n)

    print(f"{'n':>3} {'float64 err':>16} {'btfloat24 err':>16}")
    for i in range(0, n + 1, 5):
        err_f64 = float(Decimal(f64[i]) - ref[i])
        err_bt = float(Decimal(bt[i]) - ref[i])
        print(f"{i:>3} {err_f64:>16.6e} {err_bt:>16.6e}")
