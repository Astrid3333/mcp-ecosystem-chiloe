# verificador_padron

Script para cruzar un padrón electoral (o lista de firmas) contra una lista
de referencia (ej. registros de defunción, residentes en el extranjero) y
generar candidatos a revisión manual.

## Qué hace y qué no hace

- Genera una lista de candidatos a revisar (CSV). **No borra, invalida ni
  certifica nada por sí mismo.**
- Requiere coincidencia de nombre (fuzzy) + fecha de nacimiento, o un
  identificador único exacto (ej. últimos 4 dígitos de SSN), para reducir
  falsos positivos. El emparejamiento por nombre solo es notoriamente
  propenso a error (homónimos, transliteraciones, errores de tipeo).

## Contexto legal a tener en cuenta (EE.UU.)

- La *National Voter Registration Act* (NVRA) y las leyes estatales regulan
  cómo y cuándo se puede remover a alguien del padrón; en general exigen
  notificación previa y un proceso, no una baja automática por un cruce de
  datos.
- El acceso a padrones electorales y a registros de defunción varía por
  estado: muchos requieren una solicitud formal de registros públicos y
  tienen restricciones sobre el uso que se le puede dar a esos datos.
- Históricamente, programas de cruce de datos a gran escala (ej. Crosscheck)
  han producido muchos falsos positivos por depender solo del nombre y la
  fecha de nacimiento. Trata cualquier "coincidencia" como punto de partida
  para verificar, no como conclusión.

## Uso

```bash
pip install rapidfuzz --break-system-packages
python3 verificador_padron.py padron.csv referencia.csv \
    --col-nombre nombre --col-fecha fecha_nacimiento --col-id id_unico \
    --umbral 90 --salida coincidencias.csv
```

`padron_ejemplo.csv` y `referencia_ejemplo.csv` son datos sintéticos de
prueba (no corresponden a personas reales).
