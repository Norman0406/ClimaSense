// MQTT settings as one record, and the rules for valid values. Pure, tested on the PC. Like the
// network settings: build defaults (Kconfig), overridden by what the portal stored in NVS.
#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

#include "net/settings.h"

namespace telemetry {

struct MqttSettings {
    net::Text<63> host;        // host name or IPv4 address; empty: MQTT off
    uint16_t port = 1883;
    net::Text<63> username;    // empty: no login
    net::Text<63> password;
    net::Text<63> base_topic{"climasense"};  // topics: <base>/<device id>/state and .../status
    bool ha_discovery = false; // publish Home Assistant discovery messages
    net::Text<31> ha_prefix{"homeassistant"};  // Home Assistant's discovery prefix
};

enum class MqttProblem : uint8_t {
    HostCharacters,       // letters, digits, '.', '-' only
    Port,                 // 1..65535
    PasswordWithoutUser,  // MQTT only sends a password together with a user name
    BaseTopic,
    HaPrefix,
};

constexpr const char *to_string(MqttProblem problem)
{
    switch (problem) {
    case MqttProblem::HostCharacters:      return "the broker must be a host name or IPv4 address";
    case MqttProblem::Port:                return "the port must be between 1 and 65535";
    case MqttProblem::PasswordWithoutUser: return "a password needs a user name";
    case MqttProblem::BaseTopic:           return "the topic may only contain letters, digits, '-', '_' and '/' between levels";
    case MqttProblem::HaPrefix:            return "the Home Assistant prefix may only contain letters, digits, '-', '_' and '/'";
    }
    return "?";
}

std::optional<MqttProblem> validate(const MqttSettings &settings);

inline bool mqtt_configured(const MqttSettings &settings) { return !settings.host.empty(); }

// A topic or prefix: one or more levels of letters, digits, '-' and '_', separated by single '/',
// none empty (so no leading, trailing or double '/'), and no MQTT wildcards.
bool valid_topic(std::string_view topic);

}  // namespace telemetry
