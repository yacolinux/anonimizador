# Changelog

## 2026-05-30

### Added
- HAProxy integrado en `docker-compose.ha.yml` para levantar stack HA completo en un solo comando.
- Nueva config `haproxy.ha.cfg` para backend Docker (`web1..web5`) con healthcheck sobre `/ready`.
- Endpoint de app balanceada en `http://localhost:8081` y stats en `http://localhost:8404/stats`.
- Endpoint `POST /reanalyze-ai` para reintento de IA sobre archivo ya subido.
- Pagina 503 custom `haproxy-503.http` con auto-reintento cada 10 segundos.

### Changed
- Balanceo publico ajustado a `leastconn` + afinidad por IP (`stick-table` + `stick on src`) para mantener el flujo `/upload` -> `/export` en la misma instancia.
- Se mantiene sticky por cookie para rutas admin (`/admin/*`).
- Flujo IA local: healthcheck HTTP del proveedor + semaforo Redis de concurrencia + estados `ai_status`/`analysis_mode` + `queue_notice`.
- Frontend: popup `Proveedor ocupado` con reintento cada 5s, `Continuar sin IA` y `Reintentar con IA`.
- Documentacion actualizada para reflejar arquitectura y operacion HA actual:
  - `README.md`
  - `HAPROXY.md`
  - `OPERACION-HA.md`
  - `AGENTS.md`
  - `ACCESO-CONCURRENTE-PLAN.md`

### Verified
- Modo single-instance funcional (`docker-compose.yml`):
  - `GET /ready` en `http://localhost:5000/ready` responde `200`.
  - Flujo `upload -> export` (DOCX) responde `200`.
- Modo HA funcional (`docker-compose.ha.yml`):
  - `GET /ready` por HAProxy en `http://localhost:8081/ready` responde `200`.
  - Flujo `upload -> export` por HAProxy responde `200`.
  - Stats HAProxy accesibles en `http://localhost:8404/stats`.

### Notes
- En este entorno `:8080` estaba ocupado; por eso HAProxy se expone en `:8081`.
- Si se requiere `http://localhost:80`, cambiar el mapeo de puertos de `haproxy` en `docker-compose.ha.yml` a `80:80`.
