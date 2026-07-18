# HTTP-to-MQTT Gateway (STILL UNDER DEV AND TESTING)

Multi-tenant HTTP-to-MQTT gateway for ESPHome devices. Users hit a FastAPI REST API; the gateway translates authenticated requests into MQTT commands aimed at that user's own devices, and separately keeps a live cache of device state pulled from MQTT in the background.

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/) package manager
- Docker + Compose v2

## Quick Start (API only)

> [!WARNING]
> Copy `.env.example` to `.env` and fill in your values before running any of the below.

```bash
# Clone the repo
git clone https://github.com/AX1111YT/http-to-mqtt-gateway.git

# Change directory
cd http-to-mqtt-gateway

# Install dependencies
uv sync

# Create the initial admin account (prints admin API key once)
uv run scripts/bootstrap_admin.py

# Start the server
uv run uvicorn gateway.main:app --workers 1
```

## Docker

Everything lives in `deploy/prod/`. Clone the repo, configure, and run:

```bash
# Clone the repo
git clone https://github.com/AX1111YT/http-to-mqtt-gateway.git

# Change directory
cd http-to-mqtt-gateway/deploy/prod

# 1. Fill in your environment
cp .env.example .env
nano .env

# 2. Replace yourdomain.com with your actual domains
nano caddy/Caddyfile
nano mosquitto/mosquitto.conf

# 3. Start everything
docker compose up -d
```

On first start:

- Caddy auto-provisions TLS certificates from Let's Encrypt for both domains
- The API container prints admin API key (check `sudo docker compose logs api`)
- Mosquitto picks up its TLS cert from the Caddy volume automatically

> [!NOTE]
> If `BACKUP_ENABLED=False`, remove the `backup` service from `docker-compose.yml`.

## Environment Variables

| Variable                  | Required        | Default                               | Description                                         |
| ------------------------- | --------------- | ------------------------------------- | --------------------------------------------------- |
| `ENV`                     | No              | `development`                         | Set to `production` to disable interactive API docs |
| `DATABASE_URL`            | No              | `sqlite+aiosqlite:///./db/gateway.db` | SQLAlchemy async database URL                       |
| `BACKUP_ENABLED`          | No              | `False`                               | Enable daily encrypted backups to Backblaze B2      |
| `GRAFANA_LOGGING_ENABLED` | No              | `False`                               | Ship audit logs to Grafana Loki                     |
| `MQTT_BROKER_HOST`        | Yes             |                                       | MQTT broker hostname                                |
| `MQTT_BROKER_PORT`        | No              | `8883`                                | MQTT broker TLS port                                |
| `MQTT_CA_CERTS`           | No              | `""`                                  | Path to CA certificate for MQTT TLS                 |
| `MQTT_ADMIN_USERNAME`     | Yes             |                                       | Mosquitto dynamic-security admin username           |
| `MQTT_ADMIN_PASSWORD`     | Yes             |                                       | Mosquitto dynamic-security admin password           |
| `MQTT_DISCOVERY_PREFIX`   | No              | `homeassistant`                       | MQTT discovery prefix for entity auto-registration  |
| `B2_BUCKET_NAME`          | When backup on  |                                       | Backblaze B2 bucket for encrypted backups           |
| `B2_APPLICATION_KEY_ID`   | When backup on  |                                       | B2 application key ID                               |
| `B2_APPLICATION_KEY`      | When backup on  |                                       | B2 application key                                  |
| `B2_ENDPOINT_URL`         | When backup on  |                                       | B2 S3-compatible endpoint URL                       |
| `BACKUP_ENCRYPTION_KEY`   | When backup on  |                                       | Fernet key for encrypting backup files              |
| `LOKI_PUSH_URL`           | When logging on |                                       | Grafana Loki push endpoint                          |
| `LOKI_USERNAME`           | When logging on |                                       | Loki username                                       |
| `LOKI_PASSWORD`           | When logging on |                                       | Loki password                                       |
| `RATE_LIMIT_READ`         | No              | `60/minute`                           | Read endpoint rate limit                            |
| `RATE_LIMIT_WRITE`        | No              | `20/minute`                           | Write endpoint rate limit                           |
| `LOG_LEVEL`               | No              | `INFO`                                | Python logging level                                |

## Registering a Device

1. Create a user (admin endpoint):

   ```bash
   curl -X POST https://api.yourdomain.com/api/v1/admin/users \
     -H "Authorization: Bearer <admin-api-key>" \
     -H "Content-Type: application/json" \
     -d '{"display_name": "Alice"}'
   ```

   Response includes the user's API key (shown once) and UUID.

2. Register a device:

   ```bash
   curl -X POST https://api.yourdomain.com/api/v1/user/<user-uuid>/devices \
     -H "Authorization: Bearer <user-api-key>" \
     -H "Content-Type: application/json" \
     -d '{"name": "Living Room Sensor"}'
   ```

   Response includes the device's MQTT username and password (shown once) and the `topic_prefix` (which equals the device UUID).

3. Configure the ESPHome device's MQTT section:

```yaml
mqtt:
  broker: mqtt.yourdomain.com
  port: 8883
  username: <mqtt_username from step 2>
  password: <mqtt_password from step 2>
  discovery: true
  discovery_prefix: homeassistant
```

## API Endpoints

All endpoints are prefixed with `/api/v1`.

| Method   | Path                                               | Auth        | Description                  |
| -------- | -------------------------------------------------- | ----------- | ---------------------------- |
| `GET`    | `/health`                                          | None        | Health check                 |
| `POST`   | `/admin/users`                                     | Admin       | Create a user                |
| `GET`    | `/admin/users`                                     | Admin       | List all users               |
| `GET`    | `/admin/users/{uuid}`                              | Admin       | Get user details             |
| `DELETE` | `/admin/users/{uuid}`                              | Admin       | Delete a user                |
| `POST`   | `/admin/users/{uuid}/rotate-key`                   | Admin       | Rotate a user's API key      |
| `GET`    | `/admin/devices`                                   | Admin       | List all devices             |
| `GET`    | `/admin/audit-log`                                 | Admin       | Read full audit log          |
| `GET`    | `/user/{uuid}`                                     | Owner/Admin | Get own profile              |
| `POST`   | `/user/{uuid}/rotate-key`                          | Owner/Admin | Rotate own API key           |
| `GET`    | `/user/{uuid}/devices`                             | Owner/Admin | List user's devices          |
| `POST`   | `/user/{uuid}/devices`                             | Owner/Admin | Register a device            |
| `GET`    | `/user/{uuid}/devices/{id}`                        | Owner/Admin | Get device details           |
| `PATCH`  | `/user/{uuid}/devices/{id}`                        | Owner/Admin | Update device name           |
| `DELETE` | `/user/{uuid}/devices/{id}`                        | Owner/Admin | Delete device + MQTT account |
| `GET`    | `/user/{uuid}/devices/{id}/entities`               | Owner/Admin | List device entities         |
| `GET`    | `/user/{uuid}/devices/{id}/entities/{eid}`         | Owner/Admin | Get entity details           |
| `POST`   | `/user/{uuid}/devices/{id}/entities/{eid}/command` | Owner/Admin | Send command to entity       |
| `GET`    | `/user/{uuid}/audit-log`                           | Owner/Admin | Read own audit log           |

## Testing

to be added soon

## Lint and Type Check

to be added soon

## Project Structure

```txt
src/gateway/
├── main.py            FastAPI app factory, lifespan
├── config.py          pydantic-settings, reads .env
├── logging_setup.py   custom rotating JSONL handler
├── security/          API key hashing/verification, auth dependencies
├── db/                SQLAlchemy async models (users, devices, entities)
├── schemas/           Pydantic request/response models
├── mqtt/              client wrapper, provisioning, ingestor, publisher
├── services/          business logic
├── api/v1/            routers only — thin, delegate to services/
└── audit/             JSONL writer + Loki shipper

scripts/          operational scripts (bootstrap_admin.py, backup_sqlite.py)
deploy/prod/      self-contained production deployment (compose, caddy, mosquitto, .env.example)
migrations/       Alembic
```
