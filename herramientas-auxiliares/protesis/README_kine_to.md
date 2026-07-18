# Extensiones de Kinesiología y Terapia Ocupacional

Complemento a `munon_a_secciones.py` con consideraciones clínicas que no
estaban cubiertas por el flujo geométrico original (medidas → secciones →
espesor variable).

Ninguna herramienta de este módulo reemplaza el juicio clínico del
kinesiólogo, terapeuta ocupacional o protesista tratante, ni la prueba
física en el paciente. Son ayudantes geométricos/organizativos.

## 1. Trim line (línea de recorte proximal) — Kinesiología

La altura del borde proximal del socket determina cuánto rango de
movimiento le queda a la articulación vecina (ej. flexión de rodilla en
trans-tibial). Se define como offset respecto a un landmark anatómico
(ej. hueco poplíteo), no como valor absoluto, para que se adapte al
tamaño real del muñón.

`definir_trim_line()` + `advertir_secciones_sobre_trim_line()` marcan qué
secciones del `cross_section_stack` quedarían por encima del corte y
deberían excluirse del modelo final.

## 2. Familia de liners por volumen fluctuante — Kinesiología

El volumen del muñón cambia durante el día (edema) y a lo largo de los
primeros meses post-amputación (atrofia). `growth_socket_operations` ya
existe para tallas de crecimiento pediátrico — `familia_liners_por_volumen()`
reutiliza la misma lógica (shell fijo + liners intercambiables) para este
caso de uso distinto: el shell exterior se dimensiona para el volumen
máximo esperado (peor caso), y los liners más finos se usan cuando el
muñón está más pequeño.

## 3. Screening de pistoning — Kinesiología

"Pistoning" es el deslizamiento del muñón dentro del socket al caminar,
señal de suspensión insuficiente. Se aproxima geométricamente comparando
el contacto socket-muñón en dos condiciones (cargado vs. descargado) con
`contact_pressure_operations`. `plan_screening_pistoning()` documenta las
dos llamadas necesarias y cómo interpretar la diferencia — es un proxy
geométrico, no reemplaza la observación clínica de la marcha.

## 4. Tiempo de calce (donning/doffing) — Terapia Ocupacional

La independencia para ponerse y sacarse la prótesis solo es un objetivo
central de TO. `fitting_history_operations` ya registra `donning_time_sec`
por sesión; `evaluar_independencia_calce()` interpreta esa serie temporal
y marca una alerta si el promedio supera un umbral configurable, sugiriendo
revisar la geometría de entrada del socket.

## 5. Ventana de inspección de piel — Kinesiología / TO

Relevante en pacientes con sensibilidad reducida (ej. neuropatía
diabética), donde hay que poder revisar la piel sin desmontar todo el
dispositivo. `organic_operations` no tiene una operación nativa de
"cutout" — `definir_ventana_inspeccion()` describe los parámetros
deseados; la ejecución real requiere una resta booleana con
`freecad:part_operations` (operación "cut") sobre el sólido ya generado,
en una zona alejada de los landmarks de carga.

## 6. Metadata clínica (alineación y dispositivo terminal / ADL)

`PLANTILLA_ALINEACION` y `DISPOSITIVOS_TERMINALES_ADL` son diccionarios de
contexto, no geometría calculada. La alineación protésica real se ajusta
en el banco de alineación con el paciente de pie y caminando — estos
campos solo documentan la prescripción junto al modelo. El mapeo de
dispositivos terminales a actividades de la vida diaria (ADL) ayuda a
justificar, desde TO, por qué se eligió un gancho voluntario, una mano
mioeléctrica o una pinza pasiva para un paciente concreto.

## Pendiente / fuera de alcance de este módulo

- Alineación protésica calculada automáticamente: requiere banco de
  alineación físico y ajuste dinámico, no es puramente geométrico.
- Feedback sensorial/propioceptivo (mapeo de sensores de presión):
  combina electrónica y geometría, queda fuera del alcance actual del
  conector FreeCAD.
