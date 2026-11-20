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

#include "sensors/snapshot.h"

namespace telemetry {

std::string state_topic(std::string_view base_topic, std::string_view device_id);   // <base>/<id>/state
std::string status_topic(std::string_view base_topic, std::string_view device_id);  // <base>/<id>/status

inline constexpr std::string_view kOnline = "online";
inline constexpr std::string_view kOffline = "offline";

// JSON string contents: escapes '"', '\\' and control characters; UTF-8 passes through.
std::string json_escape(std::string_view text);

// value / scale with `decimals` digits, rounded half away from zero: fixed(22415, 1000, 2) ==
// "22.42", fixed(-50, 1000, 2) == "-0.05".
std::string fixed(int64_t value, int64_t scale, int decimals);

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
