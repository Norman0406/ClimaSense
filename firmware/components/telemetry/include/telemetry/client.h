// The MQTT client (espressif/mqtt): connection, online/offline status, Home Assistant discovery,
// and the state messages the app task hands over once per interval.
#pragma once

#include <optional>
#include <string>

#include "esp_err.h"

#include "diagnostics/log_line.h"
#include "telemetry/mqtt_settings.h"

namespace telemetry {

inline constexpr uint32_t kPublishIntervalS = 60;

// The build defaults (Kconfig "ClimaSense MQTT"); settings saved in the portal take precedence.
MqttSettings default_settings();

struct Identity {
    std::string device_id;         // the client ID and part of every topic
    std::string name;              // display name, for the messages and Home Assistant
    std::string firmware_version;
};

// Starts the client and returns; it connects, and reconnects, in the background once the network
// is up. On every connection it publishes "online" (retained) on the status topic, which the
// broker replaces with "offline" (the last will) if the device disappears; with Home Assistant
// discovery on, it also publishes the discovery messages, and again whenever Home Assistant
// announces a restart. Does nothing when no broker is configured. Call once.
esp_err_t start(const MqttSettings &settings, const Identity &identity);

bool connected();

// Queues a state message (QoS 1, not retained) and returns at once. False if not connected: the
// message is dropped, the next one follows an interval later.
bool publish_state(const std::string &json);

// True once the broker has acknowledged the last state message queued (for the status LED).
bool state_delivered();

// Queues a message with the Bluetooth tags heard (telemetry::ble_json; QoS 0, not retained);
// false if not connected. A lost message costs little: the next one follows within a minute.
bool publish_ble(const std::string &json);

// The boot report (telemetry::boot_json). Call before start(): it is published (QoS 1, retained)
// on the first connection, and again on later ones until the broker has acknowledged it.
void set_boot_report(std::string json);
bool boot_report_delivered();

// Queues a log message (QoS 0, not retained); false if not connected.
bool publish_log(const std::string &json);

// A log level received on <base>/<id>/set/log_level since the last call, if any.
std::optional<diagnostics::LogLevel> take_log_level_request();

// The payload of an update command received on <base>/<id>/set/ota since the last call, if any
// (parsed by ota::parse_update_command).
std::optional<std::string> take_update_request();

// Queues an update status message on <base>/<id>/ota (QoS 1, not retained).
bool publish_update_status(const std::string &json);

}  // namespace telemetry
