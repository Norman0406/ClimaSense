// The MQTT messages: topics, the state JSON, Home Assistant discovery. Pure, tested on the PC.
//
// The state message is one flat JSON object of numbers (plus id, name and time as strings): the
// shape mqtt-exporter turns into one Prometheus metric per field, and Home Assistant reads with a
// value template. A value without data is left out, never sent as 0. Every value is from the last
// interval, except CO2 (measured every 5 minutes), which repeats its latest value and comes with
// its age, co2_age_s (decided 2026-11-20).
#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "ble/sightings.h"
#include "diagnostics/log_line.h"
#include "sensors/snapshot.h"

namespace telemetry {

std::string state_topic(std::string_view base_topic, std::string_view device_id);   // <base>/<id>/state
std::string status_topic(std::string_view base_topic, std::string_view device_id);  // <base>/<id>/status

std::string boot_topic(std::string_view base_topic, std::string_view device_id);       // <base>/<id>/boot
std::string log_topic(std::string_view base_topic, std::string_view device_id);        // <base>/<id>/log
std::string log_level_topic(std::string_view base_topic, std::string_view device_id);  // <base>/<id>/set/log_level
std::string update_topic(std::string_view base_topic, std::string_view device_id);     // <base>/<id>/set/ota
std::string update_status_topic(std::string_view base_topic, std::string_view device_id);  // <base>/<id>/ota

inline constexpr std::string_view kOnline = "online";
inline constexpr std::string_view kOffline = "offline";

// JSON string contents: escapes '"', '\\' and control characters; UTF-8 passes through.
std::string json_escape(std::string_view text);

// value / scale with `decimals` digits, rounded half away from zero: fixed(22415, 1000, 2) ==
// "22.42", fixed(-50, 1000, 2) == "-0.05".
std::string fixed(int64_t value, int64_t scale, int decimals);

// Valid UTF-8 for a JSON string: bytes that do not form valid UTF-8 become '?'. For log text,
// which may contain anything.
std::string sanitize_utf8(std::string_view text);

// strftime's "%z" offset "+0100" written as RFC 3339's "+01:00" at the end of a time stamp.
std::string rfc3339_offset(std::string_view time_with_z);

struct StateMeta {
    std::string_view device_id;
    std::string_view name;   // display name (the ID if none is set)
    std::string_view time;   // RFC 3339 local time; empty before the clock is set: left out
    std::optional<int> rssi_dbm;
    uint32_t uptime_s = 0;
};

std::string state_json(const sensors::SensorSnapshot &snapshot, const StateMeta &meta);

// --- Bluetooth tags ------------------------------------------------------------------------------

std::string ble_topic(std::string_view base_topic, std::string_view device_id);  // <base>/<id>/ble

struct BleMeta {
    std::string_view device_id;
    std::string_view time;  // RFC 3339 local time; empty before the clock is set: left out
    uint32_t now_s = 0;     // uptime, the clock the report's sightings were stamped with
};

// The Find Hub tags heard since the last message (ble/sightings.h), for a service that knows the
// tags' keys: {"id":...,"time":...,"window_s":60,"fhn":[{"eid":"<hex>","type":64,"flags":"<hex>",
// "rssi":-71,"count":12,"age_s":3}]}. `type` is the frame type (64 or 65), `rssi` the strongest
// in the window, `count` the frames heard, `age_s` the time since the last one; `flags` and
// `rssi` are left out when the tag or the controller gave none, "dropped" appears when frames
// found no room in the table. An empty list says the board listened and heard no tag. Its own
// topic, not part of the state message, which stays flat numbers for Prometheus.
std::string ble_json(const ble::Report &report, const BleMeta &meta);

// --- Diagnostics -------------------------------------------------------------------------------

struct CrashInfo {
    std::string_view reason;
    std::string_view task;
    uint32_t pc = 0;
    uint32_t mcause = 0;
    uint32_t mtval = 0;
    uint32_t ra = 0;
    uint32_t sp = 0;
    std::string_view build;
    bool this_build = false;
    bool from_this_reset = false;
};

struct BootInfo {
    std::string_view device_id;
    std::string_view name;
    std::string_view firmware_version;
    std::string_view build_id;
    std::string_view reset_reason;
    std::string_view previous_log;  // the log lines kept from before the reset; may be empty
    bool on_trial = false;          // a new firmware not yet confirmed after an update
    std::optional<CrashInfo> crash;
};

// The boot report: published once per start (QoS 1, retained), on <base>/<id>/boot. Register
// values as hex strings ("0x4200a3c4"), the previous log as one string with \n line breaks.
std::string boot_json(const BootInfo &info);

// One log line as a message on <base>/<id>/log: {"level":"W","tag":...,"t_ms":...,"msg":...}.
// Text that is not an ESP-IDF log line is sent as the message alone.
std::string log_json(std::string_view line);

// The note sent when log lines were not sent (rate limit or full queue).
std::string dropped_log_json(uint32_t count);

// --- Home Assistant discovery ----------------------------------------------------------------

struct DiscoveryInfo {
    std::string_view prefix;      // usually "homeassistant"
    std::string_view base_topic;
    std::string_view device_id;
    std::string_view device_name;
    std::string_view firmware_version;
};

struct Message {
    std::string topic;
    std::string payload;
};

// One retained message per value, to <prefix>/sensor/<id>/<field>/config.
std::vector<Message> discovery_messages(const DiscoveryInfo &info);

// The topic Home Assistant announces itself on ("online" after it restarts).
std::string ha_status_topic(std::string_view prefix);

}  // namespace telemetry
