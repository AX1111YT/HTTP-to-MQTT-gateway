# HTTP-to-MQTT Gateway (STILL UNDER DEV AND TESTING)

Multi-tenant HTTP-to-MQTT gateway for ESPHome devices. Users hit a FastAPI REST API; the gateway translates authenticated requests into MQTT commands aimed at that user's own devices, and separately keeps a live cache of device state pulled from MQTT in the background.

## Prerequisites

(API only)
- Python 3.14
- [uv](https://docs.astral.sh/uv/) package manager

(Docker Deployment)
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

# Make the script executable
chmod +x mosquitto/entrypoint.sh

# 1. Fill in your environment
cp .env.example .env
nano .env  # (Fill the environmental variables)

# 2. Replace yourdomain.com with your actual MQTT domain in the Caddyfile
nano caddy/Caddyfile

# 3. Start everything
docker compose up -d
```

On first start:

- Caddy auto-provisions TLS certificates from Let's Encrypt for both domains
- Mosquitto auto-initializes its dynamic-security config (using `MQTT_ADMIN_PASSWORD` from `.env`)
- The API container prints admin API key (check `sudo docker compose logs api`)

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
| `MQTT_DOMAIN`             | Yes             |                                       | MQTT broker domain (used for TLS cert paths)        |
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

   Response includes the device's MQTT username and password (shown once) and the `topic_prefix` - a short random MQTT topic scope, distinct from the device UUID, used as the root of the device's topics on the broker.

3. Configure the ESPHome device:

```yaml
esphome:
  name: <topic_prefix from step 2>
  name_add_mac_suffix: false

mqtt:
  broker: mqtt.yourdomain.com
  port: 8883
  username: <mqtt_username from step 2>
  password: <mqtt_password from step 2>
  topic_prefix: <topic_prefix from step 2>
  discovery: true
  discovery_prefix: homeassistant
  certificate_authority: !secret mqtt_ca_cert
```

   `esphome.name` must exactly equal `topic_prefix` (and `name_add_mac_suffix` must be off) — the gateway matches discovery messages against that value, and the MQTT ACL only allows topics under it.

4. Paste Let's encrypt root certificate in mqtt_ca_cert
```
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
```

Alternatively, you can find it here: https://letsencrypt.org/certs/isrgrootx1.pem

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
