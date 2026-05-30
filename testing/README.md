# Testing

Scripts iniciales para smoke testing operativo (paso previo a tests formales).

## Scripts

- `testing/lib.sh`: helper compartido (logs, asserts HTTP, validaciones JSON).
- `testing/smoke_single.sh`: smoke test para `docker-compose.yml` (1 instancia).
- `testing/smoke_ha.sh`: smoke test para `docker-compose.ha.yml` (HAProxy + 5 instancias).
- `testing/run_all.sh`: ejecuta `smoke_single.sh` + `smoke_ha.sh` en secuencia.

## Run completo

```bash
./testing/run_all.sh
```

## Smoke test single

```bash
./testing/smoke_single.sh
```

Valida:

- levantado de stack single
- `ready` en `http://localhost:5000/ready`
- flujo `upload -> export`

## Smoke test HA

Que valida:

- levantado de `docker-compose.ha.yml`
- `ready` y `stats` via HAProxy
- flujo `upload -> export`
- pagina 503 de espera con auto-refresh cada 10s cuando no hay backends
- recuperacion al reactivar `web1..web5`

Uso:

```bash
./testing/smoke_ha.sh
```

Logs:

- Se guardan en `testing/logs/`
- Formato: `smoke-ha-YYYYmmdd-HHMMSS.log`
