#!/bin/sh
set -e

CONF_TEMPLATE="/mosquitto/config/mosquitto.conf.template"
CONF_FILE="/mosquitto/config/mosquitto.conf"
DYNSEC_FILE="/mosquitto/config/dynamic-security/dynamic-security.json"

if [ -z "$MQTT_DOMAIN" ]; then
    echo "ERROR: MQTT_DOMAIN not set. Add it to your .env file."
    exit 1
fi

sed "s/__MQTT_DOMAIN__/$MQTT_DOMAIN/g" "$CONF_TEMPLATE" > "$CONF_FILE"

if [ ! -f "$DYNSEC_FILE" ]; then
    if [ -z "$MQTT_ADMIN_PASSWORD" ]; then
        echo "ERROR: dynamic-security.json not found and MQTT_ADMIN_PASSWORD not set."
        echo "Set MQTT_ADMIN_PASSWORD in your .env file and restart."
        exit 1
    fi
    echo "Initializing dynamic-security.json (first run)..."
    mosquitto_ctrl dynsec init "$DYNSEC_FILE" admin "$MQTT_ADMIN_PASSWORD"
    chown 1883:1883 "$DYNSEC_FILE"
fi

exec mosquitto -c "$CONF_FILE"
