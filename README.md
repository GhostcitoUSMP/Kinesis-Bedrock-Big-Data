# Kinesis-Bedrock-Big-Data

## Integración local

El producer existente está en [`producer/producer.py`](producer/producer.py). Lee
[`data/transactions_data_muestra.csv`](data/transactions_data_muestra.csv), valida
sus 12 columnas, convierte tipos (incluido `amount` a `float` y fechas a ISO
8601) y emite un JSON por línea. En el estado actual del repositorio emite a
stdout o a un archivo; no implementa Kinesis ni requiere variables de entorno.
El pipeline importa su función `produce_events`, por lo que no duplica esa
transformación.

La integración preparada es:

`producer -> contrato Transaction -> detection.LocalDetectorSimulator -> Alert -> GenAI -> Storage`

`LocalDetectorSimulator` es únicamente un reemplazo determinista y documentado
para el detector del integrante 2. Sus reglas actuales son importe negativo,
importe igual o mayor a 100, campo `errors` no vacío y tres transacciones del
mismo cliente en cinco minutos. El detector definitivo debe devolver el mismo
contrato `Alert` o un adaptador equivalente.

## Instalación y pruebas

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

## Pipeline local

No usa AWS por defecto:

```powershell
python scripts\run_local_pipeline.py --limit 100 --explanation-limit 10
```

Los JSON quedan en `output\alerts`, `output\explanations` y
`output\metrics`. Para usar otro CSV u otra salida:

```powershell
python scripts\run_local_pipeline.py --input data\transactions_data_muestra.csv --limit 5000 --output output
```

El modo mock genera explicaciones deterministas en español y solo se ejecuta
para las alertas hasta `--explanation-limit`. No afirma que exista fraude.

## AWS opcional

Copiar `.env.example` a `.env` y exportar las variables en el entorno. Bedrock
requiere `GENAI_MODE=bedrock`, `AWS_REGION` y `BEDROCK_MODEL_ID`; S3 requiere
`STORAGE_MODE=s3`, `AWS_REGION` y `S3_BUCKET`. boto3 usa la cadena estándar de
credenciales de AWS; no se guardan credenciales en el código. No se afirma una
integración AWS operativa hasta probarla con una cuenta autorizada.

## Entrega requerida del integrante 2

Debe entregar el esquema real de alerta, el identificador de la regla, severidad,
evidencias, timestamp y política de reintentos. El detector debe aceptar el JSON
real del producer o un adaptador que lo convierta a `Transaction`, y exponer una
salida que pueda mapearse a `Alert`. GenAI y Storage no dependen de la
implementación concreta del detector.
