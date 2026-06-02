# Soporte Ollama Remoto (Privado)

Esta guia describe como configurar la pestaña **OpenCode** para que el comando de OpenCode use un servidor Ollama privado remoto (API compatible OpenAI).

## Requisitos

- Un servidor Ollama accesible desde el contenedor/app (IP o DNS resolvible).
- Endpoint OpenAI-compatible activo (normalmente termina en `/v1`).
- Al menos un modelo ya descargado en Ollama (`ollama pull ...`).
- Una API key si tu gateway reverse proxy la exige (si no exige, se puede dejar vacia).

## Configuracion parametro por parametro (tab OpenCode)

### 1) API Endpoint URL (`model_url`)

Valor recomendado:

`https://ollama.tu-dominio.com/v1`

Tambien puede ser HTTP interno:

`http://10.0.0.25:11434/v1`

Reglas:
- Debe ser URL completa con `http` o `https`.
- Debe incluir `/v1` para compatibilidad OpenAI.
- Si estas en Docker, `localhost` apunta al contenedor, no al host. Usar IP/DNS real o `host.docker.internal` cuando corresponda.

### 2) Nombre del modelo (`model_name`)

Formato esperado en este proyecto: `provider/modelo`.

Ejemplos validos:
- `ollama/llama3.1:8b`
- `ollama/qwen2.5:7b`

Nota tecnica: internamente la app toma la parte final (despues de `/`) para armar `--model`, por eso conviene mantener el prefijo `ollama/` y el nombre real del modelo al final.

### 3) API Key (`api_key`)

- Si tu endpoint remoto usa autenticacion por bearer token, cargala aqui.
- Si no requiere autenticacion, dejala vacia.

Comportamiento:
- Si `api_key` tiene valor, se usa esa key para la ejecucion de OpenCode.
- Si esta vacia, cae al valor de entorno `OPENAI_API_KEY`.

### 4) Comando opencode (`opencode_command`)

Usar el valor por defecto (recomendado):

`opencode run "{message}" --model opencode/{model} --dangerously-skip-permissions --file {file}`

Placeholders disponibles:
- `{message}`: instruccion corta para opencode.
- `{model}`: modelo derivado de `model_name`.
- `{file}`: archivo temporal con prompt + texto del documento.

Requisito obligatorio:
- El comando debe incluir `{file}`.

## Ejemplo completo (Ollama remoto)

En la pestaña **Elegir Modelo**:

- API Endpoint URL: `https://ollama.empresa.local/v1`
- Nombre del modelo: `ollama/llama3.1:8b`
- API Key: `ollama-prod-token-xxxxx` (o vacio si no aplica)
- Comando opencode: `opencode run "{message}" --model opencode/{model} --dangerously-skip-permissions --file {file}`

Guardar y probar subiendo un DOCX/PDF.

## Verificacion rapida

1. Guardar configuracion en panel admin.
2. Subir un documento de prueba.
3. Verificar que `/upload` devuelve `ai_status: "ok"` (o cola local si aplica).
4. Si falla, revisar logs:

```bash
docker compose logs --tail=200 web
```

## Modo API Directa (sin opencode)

Si preferis llamar a Ollama por HTTP directo (sin `opencode run`), usá el tab **API Directa** del panel admin:

1. En **Elegir Modelo**, configurá `model_url`, `model_name` y `api_key` como arriba.
2. En **API Directa**, activá el checkbox "Habilitar API directa OpenAI".
3. Usá el botón **Probar conexión** para verificar conectividad.
4. Subí un documento; la detección IA usará `POST {model_url}/chat/completions`.

Ventajas del modo directo:
- Menor overhead (sin subprocess).
- Logs detallados en el tab (botón **Ver logs**).
- Compatible con cualquier endpoint OpenAI-compatible (Ollama, vLLM, LiteLLM, etc.).

## Problemas comunes

- **No conecta al endpoint**: URL inaccesible desde contenedor, DNS interno incorrecto o firewall.
- **401/403**: API key incorrecta o no enviada por el gateway.
- **Modelo no encontrado**: `model_name` final no coincide con el modelo instalado en Ollama.
- **Timeout**: modelo pesado o servidor remoto saturado (el subprocess de opencode corta a 120s).
