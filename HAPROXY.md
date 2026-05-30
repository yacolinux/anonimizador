# Balanceo con HAProxy para Anonimizador

Guía práctica para distribuir carga entre 5-10 instancias de Anonimizador y evitar enviar tráfico a instancias ocupadas.

## 1) Endpoint `/ready`

La app ahora expone:

- `GET /ready`
  - `200` cuando la instancia está lista para recibir carga.
  - `503` cuando está ocupada (`busy`).
  - Respuesta JSON:

```json
{
  "ready": true,
  "busy": false,
  "inflight": 1,
  "max_inflight": 2
}
```

`max_inflight` se controla con variable de entorno:

- `READY_MAX_INFLIGHT` (default: `2`)

## 2) Configuración HAProxy (ejemplo)

También tenés una versión lista para usar en `haproxy.cfg`.

```haproxy
global
    log stdout format raw local0
    maxconn 2000

defaults
    mode http
    log global
    option httplog
    option dontlognull
    timeout connect 5s
    timeout client 120s
    timeout server 120s
    timeout queue 20s
    retries 2

frontend fe_anonimizador
    bind *:80
    default_backend be_anonimizador

backend be_anonimizador
    balance leastconn
    option httpchk GET /ready
    http-check expect status 200

    # Si querés afinado extra, podés usar "slowstart" en reinicios
    server a1 127.0.0.1:5001 check inter 2s fall 2 rise 2 maxconn 25
    server a2 127.0.0.1:5002 check inter 2s fall 2 rise 2 maxconn 25
    server a3 127.0.0.1:5003 check inter 2s fall 2 rise 2 maxconn 25
    server a4 127.0.0.1:5004 check inter 2s fall 2 rise 2 maxconn 25
    server a5 127.0.0.1:5005 check inter 2s fall 2 rise 2 maxconn 25

    # Opcionales (descomentá al habilitar web6..web10)
    # server a6 127.0.0.1:5006 check inter 2s fall 2 rise 2 maxconn 25
    # server a7 127.0.0.1:5007 check inter 2s fall 2 rise 2 maxconn 25
    # server a8 127.0.0.1:5008 check inter 2s fall 2 rise 2 maxconn 25
    # server a9 127.0.0.1:5009 check inter 2s fall 2 rise 2 maxconn 25
    # server a10 127.0.0.1:5010 check inter 2s fall 2 rise 2 maxconn 25
```

## 3) Parámetros iniciales recomendados

Para empezar con 5 instancias (y escalar luego a 10):

- **Gunicorn por instancia**
  - `--workers 2` (actual)
  - `--timeout 180`
- **App**
  - `READY_MAX_INFLIGHT=2` (alineado con 2 workers)
- **HAProxy backend**
  - `balance leastconn`
  - `maxconn 25` por server (ajustar según CPU/RAM)
  - `timeout queue 20s`

## 4) Compose para HA (5 activas, 10 preparadas)

Se incluye `docker-compose.ha.yml`:

- `web1..web5` activas por default (`5001..5005`)
- `web6..web10` comentadas (listas para habilitar)

Levantar 5 instancias:

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

Escalar a 10 instancias:

1. Descomentá `web6..web10` y volúmenes `uploads_data_6..10`
2. Descomentá `server a6..a10` en HAProxy
3. Aplicá cambios:

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

## 5) Recomendaciones operativas

- Usar la misma `FLASK_SECRET_KEY` en todas las instancias.
- Si el panel admin usa sesión y pasás por múltiples instancias:
  - ideal: storage de sesión compartido (Redis), o
  - sticky sessions en HAProxy.
- `regex_patterns.json` hoy es archivo local por instancia; para consistencia real en HA:
  - mover config a DB/Redis compartida, o
  - montar volumen compartido.

## 6) Deploy rápido de 5 instancias

Ejemplo conceptual (puertos diferentes):

- instancia 1: `5001`
- instancia 2: `5002`
- instancia 3: `5003`
- instancia 4: `5004`
- instancia 5: `5005`

HAProxy escucha en `:80` y enruta según `/ready` + `leastconn`.
