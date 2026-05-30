# Plan de Acceso Concurrente (10-20 usuarios)

## Cuellos de botella actuales

1. **Gunicorn 2 workers** → solo 2 requests simultáneos. Cada análisis de IA bloquea un worker ~10-15s
2. **`regex_patterns.json` sin locking** → race conditions si dos admins guardan config al mismo tiempo
3. **Sesiones Flask en memoria** → no se comparten entre workers
4. **Sin cleanup de uploads** → el directorio crece indefinidamente
5. **Config global** → un solo prompt/patrones para todos los usuarios

## Arquitectura propuesta

```
                    ┌─────────────┐
                    │   Nginx/LB  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ Gunicorn  │ │Gunicorn│ │ Gunicorn │
        │ 8 workers │ │8 wks   │ │ 8 wks    │
        │  gevent   │ │        │ │          │
        └─────┬─────┘ └───┬────┘ └────┬─────┘
              └───────────┼───────────┘
                          │
                    ┌─────▼─────┐
                    │   Redis   │ ← Sesiones + Cola + Cache config
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  Celery   │ ← Workers IA aislados (opencode run)
                    │ Workers   │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  S3 / FS  │ ← Uploads con TTL
                    └───────────┘
```

## Implementación por fases

### Fase 1 — Inmediata (sin infra nueva)

- `gunicorn --workers 8 --worker-class gevent --timeout 180`
  - `gevent` permite que los workers no se bloqueen en el subprocess de opencode
- `Flask-Session` con Redis backend para sesiones compartidas entre workers
- `fcntl` file locking en `save_regex_config()` para evitar race conditions
- Cron job o TTL para limpiar `/app/uploads` cada 24h

### Fase 2 — Cola de tareas IA

- Celery + Redis: el endpoint `/upload` retorna inmediatamente con un `job_id`
- WebSocket o Server-Sent Events para notificar al frontend cuando la IA termine
- Los workers de Flask nunca se bloquean esperando a opencode
- Permite escalar workers de IA independientemente del web tier

### Fase 3 — Multi-tenant (si se necesita)

- PostgreSQL para usuarios, sesiones, historial de documentos
- Configuraciones por usuario (cada uno tiene sus patrones/prompt/modelo)
- Autenticación JWT o session-based por usuario
- Rate limiting por IP/usuario
- S3 para almacenamiento de uploads con expiración automática

## Estimación de capacidad

| Configuración | Usuarios concurrentes |
|---|---|
| Actual (2 workers sync) | ~2-3 |
| 8 workers gevent | ~15-20 |
| + Celery (4 workers IA) | ~30-40 |
| + Nginx LB + 2 instancias | ~60-80 |
