# Kinesis-Bedrock-Big-Data

## Integración local

El producer existente está en [`producer/producer.py`](producer/producer.py). Lee
[`data/transactions_data_muestra.csv`](data/transactions_data_muestra.csv), valida
sus 12 columnas, convierte tipos (incluido `amount` a `float` y fechas a ISO 8601) y emite un JSON por línea. En el estado actual del repositorio emite a
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

# Detección de anomalías en transacciones con Kinesis y Bedrock

Prototipo educativo de streaming. Kinesis transporta eventos; Lambda agrega por tarjeta y minuto UTC; DynamoDB conserva métricas e idempotencia; una regla determinista detecta velocidad inusual; Bedrock (opcional) explica la alerta; S3 guarda solo el resultado de la alerta. La alerta indica comportamiento inusual y **no confirma fraude**.

```text
CSV -> productor Python -> Kinesis -> Lambda -> DynamoDB (ventana e idempotencia)
                                          |-> Bedrock (solo con alerta y modelo configurado)
                                          `-> S3 (JSON de alerta)
```

La infraestructura se define en `template.yaml` (AWS SAM/CloudFormation). Este repositorio queda preparado para desplegarla, pero no crea recursos automáticamente. No se incluyen credenciales.

## Contenido

| Ruta                    | Uso                                                                      |
| ----------------------- | ------------------------------------------------------------------------ |
| `producer/producer.py`  | Convierte CSV a JSONL local o envía eventos a Kinesis con `boto3`.       |
| `detection/detector.py` | Funciones puras para ventanas UTC, métricas y regla de velocidad.        |
| `lambda_function.py`    | Consumidor de Kinesis, estado idempotente por evento y coordinación AWS. |
| `genai/explainer.py`    | Explicación en español mediante Bedrock Converse API.                    |
| `storage/storage.py`    | Persistencia de alertas JSON en S3.                                      |
| `tests/`                | Pruebas unitarias locales, sin llamadas a AWS.                           |
| `template.yaml`         | Stream, función, DynamoDB, S3, permisos y trigger Kinesis.               |

## Contrato de evento

Cada línea enviada a Kinesis es un objeto JSON UTF-8. `id`, `date`, `card_id` y `amount` son necesarios para detección; el productor también conserva los campos del dataset para trazabilidad local. Los identificadores de cliente y tarjeta del dataset son identificadores sintéticos, no números de tarjeta.

```json
{
  "id": 7475328,
  "date": "2010-01-01T00:02:00",
  "client_id": 561,
  "card_id": 4575,
  "amount": 14.57,
  "use_chip": "Swipe Transaction",
  "merchant_id": 67570,
  "merchant_city": "Bettendorf",
  "merchant_state": "IA",
  "zip": "52722",
  "mcc": 5311,
  "errors": null
}
```

Las fechas sin zona horaria se interpretan como UTC (asunción para este dataset). Las ventanas son fijas de 60 segundos en UTC, calculadas a partir de la fecha del evento. La regla inicial marca al menos cinco transacciones de una tarjeta en una ventana; es un umbral de demostración configurable, no una conclusión estadística ni una clasificación de fraude. Importes negativos se admiten como valores del dataset y no son anomalías por sí solos.

La alerta guardada en S3 tiene `schema_version`, `alert_id`, `window_start`, métricas agregadas y `rules`; su `explanation` será nula si Bedrock no está configurado. No se envían a Bedrock eventos individuales, identificadores de alerta/tarjeta ni datos del comercio. La explicación usa únicamente métricas agregadas y la regla activada. Los resultados se mantienen 30 días en S3; el estado temporal y recibos de idempotencia usan TTL de DynamoDB.

## Preparación local

Requisitos: Python 3.10+ (la Lambda usa Python 3.13), AWS CLI v2 solo para despliegue, AWS SAM CLI solo para empaquetar/desplegar. Para trabajo local no se necesitan credenciales AWS.

En PowerShell, desde la raíz:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python .\producer\producer.py --limit 1000 --output .\transactions_events.jsonl
```

`--output` sobrescribe el archivo local indicado. Usa `--input` para seleccionar otro CSV. Para inspeccionar eventos en pantalla, omite `--output`.

## Antes de desplegar en AWS

Hagan estos pasos con una cuenta de laboratorio y una región acordadas. Cada integrante puede probar sus módulos localmente; el despliegue integrado debe hacerlo una persona responsable en una cuenta común. Bedrock se deja desactivado por defecto: el acceso al modelo y sus condiciones dependen de la cuenta y región. Antes de activar el parámetro, confirmen acceso al modelo y revisen los precios vigentes de cada servicio.

1. Instalen AWS CLI v2 y SAM CLI; configuren un perfil de AWS localmente, sin guardar claves en el repositorio.
2. Comprueben cuenta, perfil y región seleccionada:

   ```powershell
   aws sts get-caller-identity --profile <perfil>
   aws configure get region --profile <perfil>
   sam --version
   sam validate --lint
   ```

3. Revisen `template.yaml`. Crea Kinesis con un shard provisionado, Lambda, DynamoDB bajo demanda, bucket S3 privado con expiración a 30 días y permisos del rol de Lambda. La política Bedrock permite invocar cualquier modelo (`Resource: "*"`); si su cuenta lo permite, sustitúyanla por el ARN del modelo concreto antes de desplegar.
4. Desplieguen de forma interactiva:

   ```powershell
   sam build
   sam deploy --guided --profile <perfil>
   ```

   Seleccionen la región acordada, acepten la creación del rol IAM de CloudFormation y guarden la configuración sugerida en `samconfig.toml` solo si no contiene datos sensibles. Dejen `BedrockModelId` vacío hasta confirmar acceso. El umbral inicial es cinco y se puede ajustar con `MaxTransactionsPerCardPerMinute`.

5. Obtengan el nombre del stream desde las salidas del stack:

   ```powershell
   aws cloudformation describe-stacks --stack-name <nombre-stack> --query "Stacks[0].Outputs" --output table --profile <perfil>
   ```

6. Envíen una muestra y una anomalía sintética controlada. Este comando envía las primeras 1.000 filas del CSV y cinco eventos sintéticos con la misma tarjeta/ventana:

   ```powershell
   python .\producer\producer.py --limit 1000 --stream-name <nombre-stream> --demo-anomaly
   ```

7. Obtengan el nombre físico de la función y bucket en las salidas/recursos de CloudFormation, luego revisen sus logs y alertas:

   ```powershell
   aws cloudformation describe-stack-resources --stack-name <nombre-stack> --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text --profile <perfil>
   aws logs tail "/aws/lambda/<nombre-funcion>" --since 10m --profile <perfil>
   aws s3 ls "s3://<bucket-resultados>/alerts/" --recursive --profile <perfil>
   ```

Para activar Bedrock, vuelvan a desplegar pasando un `BedrockModelId` permitido por su cuenta y región, por ejemplo el ID exacto que muestre la consola de Bedrock. No usen este ejemplo como garantía de disponibilidad:

```powershell
sam deploy --config-env default --parameter-overrides BedrockModelId=<id-modelo> --profile <perfil>
```

SAM puede requerir configuración guardada previamente con `sam deploy --guided`; también se puede volver a ejecutar el modo guiado e indicar el parámetro en la solicitud interactiva.

## Costos, límites y limpieza

**No se garantiza que el stack sea gratuito.** Kinesis provisionado factura por shard/tiempo y transferencia; DynamoDB bajo demanda, Lambda, CloudWatch Logs y almacenamiento/solicitudes S3 pueden generar cargos; Bedrock puede cobrar por tokens. Revisen la página de precios, la región, los créditos/cuotas disponibles y las alertas de costos de la cuenta antes del despliegue. Empiecen con un conjunto pequeño y eliminen el stack al terminar.

El bucket se crea privado y bloquea acceso público. No se suben archivos CSV a S3 ni se persisten transacciones individuales. El productor no elimina recursos ni despliega infraestructura.

Para eliminar los recursos creados por CloudFormation:

```powershell
aws cloudformation delete-stack --stack-name <nombre-stack> --profile <perfil>
aws cloudformation wait stack-delete-complete --stack-name <nombre-stack> --profile <perfil>
```

Confirmen el nombre del stack antes de borrarlo. Los objetos del bucket están configurados para expirar en 30 días, pero CloudFormation no puede eliminar un bucket con objetos; vacíen **solo el bucket de este proyecto** antes de borrar el stack si ya contiene resultados.

## Trabajo del equipo

| Integrante               | Módulo y tarea inmediata                                                                                                                                    |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Productor/Kinesis    | Revisar campos del CSV, ejecutar modo JSONL, comprobar 1.000 eventos y probar envío con el stream común.                                                    |
| 2 — Detección            | Revisar la regla inicial con la distribución real, decidir umbrales de demostración, ampliar escenarios unitarios normales/anómalos y validar ventanas UTC. |
| 3 — GenAI/almacenamiento | Verificar permisos y disponibilidad regional de Bedrock, revisar prompt/salida, validar objetos de S3 y ajustar IAM al modelo concreto si es posible.       |

Los contratos y las pruebas de integración son responsabilidad de los tres. El dashboard queda fuera de esta primera versión.

## Limitaciones que deben quedar claras en la presentación

- Los datos del dataset son históricos: Kinesis reproduce su envío, pero no convierte las marcas de tiempo antiguas en tiempo real.
- Se conserva estado incremental por tarjeta/ventana y se deduplica cada `id` durante siete días. Conteo, suma y errores se actualizan atómicamente; el máximo se actualiza por separado de forma monotónica. La invocación de Bedrock y la escritura S3 son servicios externos y no ofrecen una transacción distribuida exactamente una vez.
- Si se configuró Bedrock y el modelo no está disponible o falla, Lambda falla para que Kinesis reintente; revisen errores y reintentos en CloudWatch. Sin `BedrockModelId`, las alertas se escriben a S3 con explicación desactivada.
- La regla de velocidad es deliberadamente simple para el proyecto. No usa etiquetas de fraude y no debe presentarse como detector de fraude en producción.
