# verificador_padron

Script para cruzar un padrón electoral (o lista de firmas) contra una lista
de referencia (ej. registros de defunción, residentes en el extranjero) y
generar candidatos a revisión manual. No borra ni certifica nada por sí
mismo — ver los comentarios en `verificador_padron.py` para el contexto
legal (NVRA, acceso a registros públicos) y las limitaciones del
emparejamiento por nombre (falsos positivos).

## Uso

```bash
pip install rapidfuzz --break-system-packages
python3 verificador_padron.py padron.csv referencia.csv \
    --col-nombre nombre --col-fecha fecha_nacimiento --col-id id_unico \
    --umbral 90 --salida coincidencias.csv
```

`padron_ejemplo.csv` y `referencia_ejemplo.csv` son datos sintéticos de
prueba (no corresponden a personas reales).
