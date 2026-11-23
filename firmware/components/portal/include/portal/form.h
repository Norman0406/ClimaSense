// The portal's settings form: decoding what the browser sends and turning it into checked
// settings. Pure, tested on the PC. Uses std::string: the portal is not in the measurement path.
#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "net/settings.h"
#include "settings/device.h"
#include "telemetry/mqtt_settings.h"

namespace portal {

// Field names in the form.
namespace field {
inline constexpr std::string_view kSsid = "ssid";
inline constexpr std::string_view kPassword = "password";
inline constexpr std::string_view kOpenNetwork = "open";  // checkbox: the network has no password
inline constexpr std::string_view kName = "name";
inline constexpr std::string_view kStatusLed = "led";  // checkbox
inline constexpr std::string_view kTagScan = "tags";   // checkbox
// Hidden marker sent with the device section: with it, a missing "led" or "tags" means "off".
inline constexpr std::string_view kDeviceSection = "device_form";
inline constexpr std::string_view kCountry = "country";
inline constexpr std::string_view kSntpServer = "sntp";
inline constexpr std::string_view kTimezone = "tz";
inline constexpr std::string_view kMqttHost = "mqtt_host";
inline constexpr std::string_view kMqttPort = "mqtt_port";
inline constexpr std::string_view kMqttUser = "mqtt_user";
inline constexpr std::string_view kMqttPassword = "mqtt_pass";
inline constexpr std::string_view kMqttNoPassword = "mqtt_nopass";  // checkbox: clear the password
inline constexpr std::string_view kMqttTopic = "mqtt_topic";
inline constexpr std::string_view kHaDiscovery = "ha";              // checkbox
inline constexpr std::string_view kHaPrefix = "ha_prefix";
// Hidden marker sent with the MQTT section. Browsers leave out unticked checkboxes; with the
// marker present, a missing "ha" means "off" rather than "keep".
inline constexpr std::string_view kMqttSection = "mqtt_form";
}  // namespace field

inline constexpr std::size_t kMaxFormBytes = 2048;

// Decodes application/x-www-form-urlencoded text: '+' is a space, %XX a byte. Nothing if a
// %-escape is malformed.
std::optional<std::string> url_decode(std::string_view text);

enum class FieldStatus { Missing, Present, Malformed };

struct FormValue {
    FieldStatus status = FieldStatus::Missing;
    std::string value;
};

// The first `key=value` pair with this key in a form body.
FormValue form_value(std::string_view body, std::string_view key);

struct FieldError {
    std::string_view field;  // one of field::k...
    std::string message;
};

struct FormResult {
    net::NetSettings net;
    settings::DeviceSettings device;
    telemetry::MqttSettings mqtt;
    std::vector<FieldError> errors;
    bool ok() const { return errors.empty(); }
};

// Applies a submitted form to the current settings. A field missing from the form keeps its
// current value. The password: empty keeps the stored one, "open network" clears it; a new
// network name with an empty password field (and "open network" not ticked) is an error, so an
// old network's password is never kept for a new one by accident. The country is upper-cased.
// `net` and `device` hold the result even when there are errors, so the page can show the
// user's input again (never the password).
// MQTT: an empty password field keeps the stored password, "no password" clears it; clearing
// the user name clears the password too (MQTT only sends one with the other).
FormResult apply_form(std::string_view body, const net::NetSettings &current_net,
                      const settings::DeviceSettings &current_device,
                      const telemetry::MqttSettings &current_mqtt = {});

}  // namespace portal
