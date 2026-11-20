// The MQTT client (espressif/mqtt): connection, online/offline status, Home Assistant discovery,
// and the state messages the app task hands over once per interval.
#pragma once

#include <string>

#include "esp_err.h"

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

// Queues a state message (QoS 0, not retained) and returns at once. False if not connected: the
// message is dropped, the next one follows an interval later.
bool publish_state(const std::string &json);

}  // namespace telemetry
