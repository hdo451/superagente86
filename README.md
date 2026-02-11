# Superagente86

Pipeline en Python para leer newsletters desde Gmail (etiqueta `newsletters`), agrupar por tema exacto, extraer links y crear un Google Doc con el resumen dos veces al dia.

## Requisitos

- Python 3.10+
- Credenciales OAuth de Google (Gmail API y Google Docs API habilitadas)

## Setup rapido

1. Crea un entorno virtual e instala dependencias:

   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Copia `.env.example` a `.env` y ajusta rutas si es necesario.
3. Coloca `credentials.json` en la raiz del proyecto.
4. Ejecuta el pipeline por primera vez para generar `token.json`:

   python -m superagente86.cli --config config.yaml --dry-run

5. Ejecuta en modo normal:

   python -m superagente86.cli --config config.yaml

## Configuracion

- La etiqueta Gmail se define en `config.yaml` como `label: newsletters`.
- Horarios sugeridos: 08:30 y 13:30 (zona horaria US/Pacific).
- Cada ejecucion usa ventana por horario: 08:30 toma desde 13:30 del dia anterior; 13:30 toma desde 08:30 del mismo dia.
- El reporte se crea como un Google Doc nuevo por ejecucion.
- Las noticias repetidas se agrupan por tema exacto (subject normalizado).
- Cada noticia incluye fuentes y links extraidos del correo.

## Siguiente paso (scheduler)

Puedes usar cron o GitHub Actions para ejecutar dos veces al dia. Si quieres, lo agrego en la siguiente iteracion.
