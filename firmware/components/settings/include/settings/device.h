// Device settings: the name shown for this board, whether the status LED is on, and whether the
// board scans for Bluetooth tags. Pure, tested on the PC.
//
// The device ID (the host name, from the MAC address) is fixed and goes into the MQTT topics;
// the name is set in the portal and only travels as information, so renaming never breaks a
// subscription or splits a history (docs/decisions.md).
#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

#include "net/settings.h"

namespace settings {

struct DeviceSettings {
    net::Text<32> name;  // UTF-8, up to 32 bytes; empty: the ID is shown instead
    // The status LED (board/status_pattern.h). Off, e.g. in a bedroom: dark except while the
    // setup portal is open and when a short press on the button asks for the status.
    bool status_led = true;
    // The Bluetooth scan for Find Hub tags (ble/scanner.h), whose identifiers go out over MQTT
    // for presence detection. Off unless asked for: listening costs some heat next to the
    // temperature sensor, and not every board needs to take part.
    bool tag_scan = false;
};

enum class DeviceProblem : uint8_t {
    NameNotUtf8,
    NameControlCharacters,
};

constexpr const char *to_string(DeviceProblem problem)
{
    switch (problem) {
    case DeviceProblem::NameNotUtf8:           return "the name is not valid UTF-8 text";
    case DeviceProblem::NameControlCharacters: return "the name may not contain control characters";
    }
    return "?";
}

std::optional<DeviceProblem> validate(const DeviceSettings &settings);

// The name if set, else the ID.
inline std::string_view display_name(const DeviceSettings &settings, std::string_view device_id)
{
    return settings.name.empty() ? device_id : settings.name.view();
}

}  // namespace settings
