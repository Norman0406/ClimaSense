// Loading and saving the settings records. Pure logic on top of KvStore, tested on the PC.
//
// Each field is its own entry, so new fields can be added without migrating anything. A field
// that is stored takes precedence over the build default, even when stored empty (a network
// deliberately cleared in the portal stays cleared). Saving validates first and writes nothing
// if a value is invalid. A stored set that has become invalid is not used: load falls back to
// the defaults and says so.
#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

#include "net/settings.h"
#include "settings/device.h"
#include "settings/kv_store.h"
#include "telemetry/mqtt_settings.h"

namespace settings {

// NVS keys: at most 15 characters.
namespace key {
inline constexpr const char *kWifiSsid = "wifi_ssid";
inline constexpr const char *kWifiPassword = "wifi_pass";
inline constexpr const char *kWifiCountry = "wifi_country";
inline constexpr const char *kSntpServer = "sntp_server";
inline constexpr const char *kTimezone = "timezone";
inline constexpr const char *kDeviceName = "device_name";
inline constexpr const char *kMqttHost = "mqtt_host";
inline constexpr const char *kMqttPort = "mqtt_port";
inline constexpr const char *kMqttUser = "mqtt_user";
inline constexpr const char *kMqttPassword = "mqtt_pass";
inline constexpr const char *kMqttBaseTopic = "mqtt_topic";
inline constexpr const char *kHaDiscovery = "ha_discovery";
inline constexpr const char *kHaPrefix = "ha_prefix";
}  // namespace key

template <typename Settings>
struct Loaded {
    Settings value;
    uint8_t stored_fields = 0;   // how many fields came from the store rather than the defaults
    bool rejected = false;       // the stored values were invalid; `value` holds the defaults
    bool store_failed = false;   // reading failed; `value` holds what could be read, or defaults
};

Loaded<net::NetSettings> load_net(KvStore &store, const net::NetSettings &defaults);
Loaded<DeviceSettings> load_device(KvStore &store, const DeviceSettings &defaults);
// The port and the switch are stored as text ("1883", "1"/"0") and parsed strictly.
Loaded<telemetry::MqttSettings> load_mqtt(KvStore &store, const telemetry::MqttSettings &defaults);

enum class SaveError : uint8_t { Invalid, StoreFailed };

// Validates, then writes every field and commits. On Invalid nothing is written.
std::optional<SaveError> save_net(KvStore &store, const net::NetSettings &settings);
std::optional<SaveError> save_device(KvStore &store, const DeviceSettings &settings);
std::optional<SaveError> save_mqtt(KvStore &store, const telemetry::MqttSettings &settings);

// "1".."65535" -> the port; anything else (signs, spaces, leading zeros, 0) -> nothing.
std::optional<uint16_t> parse_port(std::string_view text);

}  // namespace settings
