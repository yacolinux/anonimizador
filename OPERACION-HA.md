# Operacion Single + HA

Guia operativa para correr Anonimizador en modo simple (1 instancia) y modo HA (5-10 instancias con HAProxy).

## 1) Modos de despliegue

### Single instance (sin HA)

```bash
docker compose up --build -d
```

- Levanta `web` + `redis` local.
- Totalmente funcional para uso normal.

### HA (5 instancias activas por default)

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

- Levanta `redis` compartido + `web1..web5`.
- `web6..web10` quedan comentadas para escalar.

## 2) Variables clave (`.env`)

- `SESSION_BACKEND=redis|cookie`
- `REDIS_URL=redis://redis:6379/0`
- `REDIS_CONFIG_KEY=anonimizador:config`
- `READY_MAX_INFLIGHT=2`
- `SESSION_COOKIE_SECURE=1` (si hay HTTPS)
- `UPLOAD_TTL_SECONDS=86400`
- `LOGIN_WINDOW_SECONDS=300`
- `LOGIN_MAX_ATTEMPTS=5`

## 3) Redis: cuando usar cada backend de sesion

- `SESSION_BACKEND=redis` (recomendado):
  - sesion admin compartida entre instancias
  - rate limit login distribuido
  - config admin distribuida (prompt/patrones/modelo)

- `SESSION_BACKEND=cookie`:
  - modo fallback/local sin dependencia de Redis para sesion

## 4) HAProxy: reglas recomendadas

- Trafico publico (`/upload`, `/export`): backend `leastconn` + health `/ready`.
- Trafico admin (`/admin/*`): backend sticky (`cookie SRV`).

Referencia: `haproxy.cfg` y `HAPROXY.md`.

## 5) Escalar de 5 a 10 instancias

1. Descomentar `web6..web10` en `docker-compose.ha.yml`.
2. Descomentar `a6..a10` en `haproxy.cfg`.
3. Aplicar cambios:

```bash
docker compose -f docker-compose.ha.yml up --build -d
```

## 6) Checklist de produccion

- [ ] `FLASK_SECRET_KEY` fuerte y unica
- [ ] `ADMIN_PASS` fuerte
- [ ] `SESSION_COOKIE_SECURE=1` con TLS
- [ ] Redis no expuesto a internet publica
- [ ] Backups de `redis_data` (si guardas config admin)
- [ ] Monitorear `/ready` y `inflight`

## 7) Verificacion rapida

```bash
curl -s http://localhost:5000/ready
curl -s http://localhost:5001/ready
```

Debe responder `ready=true` cuando la instancia esta libre y `503` cuando esta ocupada.
