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

## Alcance real

Qué logra:
- Compara dos listas (CSV) y devuelve candidatos a ser la misma persona,
  por nombre similar + misma fecha de nacimiento, o por un ID exacto.
- Sirve como primer filtro/triage: reduce miles de filas a un puñado de
  candidatos para revisión manual. Funciona para cualquier par de listas
  con nombre+fecha, no solo padrón vs. defunciones.

Qué NO logra:
- No analiza firmas manuscritas ni imágenes — no hace verificación
  biométrica ni de caligrafía. Solo compara texto de columnas en un CSV.
- No accede por sí solo a padrones reales ni a registros de defunción de
  EE.UU. — esos datos hay que obtenerlos por los canales oficiales
  (solicitud de registros públicos), y el acceso varía por estado.
- No tiene validez legal: no da de baja a nadie ni invalida una firma o
  registro. Solo produce candidatos para revisión humana.

## Compatibilidad

Python puro (csv, argparse, datetime, unicodedata de la librería estándar)
más `rapidfuzz`, que tiene wheels precompilados para Windows, Linux y Mac.
Sin rutas ni llamadas a shell específicas de un SO.

```bash
# Linux (Debian/Ubuntu)
pip install rapidfuzz --break-system-packages

# Windows / otros
pip install rapidfuzz
```

`--break-system-packages` es solo por la protección "entorno gestionado
externamente" de Debian/Ubuntu; en Windows normalmente no hace falta.

## Uso

```bash
pip install rapidfuzz --break-system-packages
python3 verificador_padron.py padron.csv referencia.csv \
    --col-nombre nombre --col-fecha fecha_nacimiento --col-id id_unico \
    --umbral 90 --salida coincidencias.csv
```

`padron_ejemplo.csv` y `referencia_ejemplo.csv` son datos sintéticos de
prueba (no corresponden a personas reales).
