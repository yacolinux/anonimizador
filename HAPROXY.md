# Balanceo con HAProxy para Anonimizador

Guía práctica para distribuir carga entre 5-10 instancias de Anonimizador y evitar enviar tráfico a instancias ocupadas.

Para operación completa (single + HA), ver `OPERACION-HA.md`.

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

## 2) Configuración HAProxy (host)

Para correr HAProxy fuera de Docker, tenés una versión lista para usar en `haproxy.cfg`.

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

### Sticky sessions para `/admin/*`

Aunque el flujo público no requiere afinidad, conviene mantener sticky para panel admin:

```haproxy
frontend fe_anonimizador
    bind *:80
    acl is_admin path_beg /admin
    use_backend be_anonimizador_admin if is_admin
    default_backend be_anonimizador

backend be_anonimizador_admin
    balance roundrobin
    cookie SRV insert indirect nocache
    option httpchk GET /ready
    http-check expect status 200

    server a1 127.0.0.1:5001 check cookie a1
    server a2 127.0.0.1:5002 check cookie a2
    server a3 127.0.0.1:5003 check cookie a3
    server a4 127.0.0.1:5004 check cookie a4
    server a5 127.0.0.1:5005 check cookie a5
```

## 4) Compose para HA (5 activas, 10 preparadas)

Se incluye `docker-compose.ha.yml` con HAProxy integrado:

- `haproxy` en el mismo stack (app en `localhost:8081`, stats en `localhost:8404`)
- `web1..web5` activas por default (`5001..5005` publicados para debug)
- `web6..web10` comentadas (listas para habilitar)
- `redis` compartido para sesiones/config/rate-limit
- pagina 503 custom (`haproxy-503.http`) con auto-refresh cada 10s cuando no hay backend disponible

Levantar 5 instancias:

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

Config usada por ese servicio: `haproxy.ha.cfg`.

Nota importante: el backend público usa afinidad por IP (`stick-table` + `stick on src`) para que el flujo `/upload` -> `/export` quede en la misma instancia y encuentre el archivo temporal.

Escalar a 10 instancias:

1. Descomentá `web6..web10` y volúmenes `uploads_data_6..10`
2. Descomentá `server a6..a10` en `haproxy.ha.cfg` (o en `haproxy.cfg` si usás HAProxy en host)
3. Aplicá cambios:

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

## 5) Recomendaciones operativas

- Usar la misma `FLASK_SECRET_KEY` en todas las instancias.
- Mantener sticky para `/admin/*` (afinidad de panel) aunque exista sesión compartida.
- Con `SESSION_BACKEND=redis` + `REDIS_URL` todas las instancias comparten sesión/rate-limit/config.

## 6) Deploy rápido de 5 instancias

Ejemplo conceptual (puertos diferentes):

- instancia 1: `5001`
- instancia 2: `5002`
- instancia 3: `5003`
- instancia 4: `5004`
- instancia 5: `5005`

Con compose HA, HAProxy escucha en `:8081` (host) y enruta según `/ready` + `leastconn`.
