#include "telemetry/payload.h"

#include <array>
#include <cstdio>

namespace telemetry {

namespace {

struct ValueInfo {
    const char *field;         // key in the state JSON
    const char *name;          // shown in Home Assistant
    const char *unit;          // nullptr: none
    const char *device_class;  // nullptr: none
    bool diagnostic;
};

// The values of the state message, in its order.
constexpr std::array<ValueInfo, 9> kValues{{
    {"temperature_c", "Temperature", "°C", "temperature", false},
    {"humidity_pct", "Humidity", "%", "humidity", false},
    {"pressure_hpa", "Pressure", "hPa", "atmospheric_pressure", false},
    {"co2_ppm", "CO2", "ppm", "carbon_dioxide", false},
    {"co2_age_s", "CO2 age", "s", "duration", true},
    {"voc_index", "VOC index", nullptr, nullptr, false},  // Home Assistant has no class for an index
    {"nox_index", "NOx index", nullptr, nullptr, false},
    {"rssi_dbm", "Wi-Fi signal", "dBm", "signal_strength", true},
    {"uptime_s", "Uptime", "s", "duration", true},
}};

void add_number(std::string &out, const char *key, const std::string &value)
{
    out += ",\"";
    out += key;
    out += "\":";
    out += value;
}

void add_string(std::string &out, const char *key, std::string_view value, bool first = false)
{
    if (!first) {
        out += ',';
    }
    out += '"';
    out += key;
    out += "\":\"";
    out += json_escape(value);
    out += '"';
}

}  // namespace

std::string state_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/state";
}

std::string status_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/status";
}

std::string ha_status_topic(std::string_view prefix) { return std::string(prefix) + "/status"; }

std::string json_escape(std::string_view text)
{
    std::string out;
    out.reserve(text.size());
    for (const char ch : text) {
        const auto c = static_cast<unsigned char>(ch);
        switch (ch) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (c < 0x20) {
                char buf[8];
                snprintf(buf, sizeof(buf), "\\u%04x", c);
                out += buf;
            } else {
                out.push_back(ch);
            }
        }
    }
    return out;
}

std::string fixed(int64_t value, int64_t scale, int decimals)
{
    int64_t factor = 1;
    for (int i = 0; i < decimals; ++i) {
        factor *= 10;
    }
    // value * factor / scale, rounded half away from zero.
    const int64_t numerator = value * factor;
    const int64_t half = scale / 2;
    const int64_t scaled = numerator >= 0 ? (numerator + half) / scale : (numerator - half) / scale;

    const int64_t magnitude = scaled < 0 ? -scaled : scaled;
    std::string out = scaled < 0 ? "-" : "";
    out += std::to_string(magnitude / factor);
    if (decimals > 0) {
        std::string fraction = std::to_string(magnitude % factor);
        out += '.';
        out.append(static_cast<std::size_t>(decimals) - fraction.size(), '0');
        out += fraction;
    }
    return out;
}

std::string rfc3339_offset(std::string_view time_with_z)
{
    std::string out(time_with_z);
    // ...+0100 -> ...+01:00
    if (out.size() >= 5) {
        const char sign = out[out.size() - 5];
        if (sign == '+' || sign == '-') {
            out.insert(out.size() - 2, ":");
        }
    }
    return out;
}

std::string state_json(const sensors::SensorSnapshot &s, const StateMeta &meta)
{
    std::string out = "{";
    add_string(out, "id", meta.device_id, true);
    add_string(out, "name", meta.name);
    if (!meta.time.empty()) {
        add_string(out, "time", meta.time);
    }
    if (s.temperature_mc) add_number(out, "temperature_c", fixed(*s.temperature_mc, 1000, 2));
    if (s.humidity_mpercent) add_number(out, "humidity_pct", fixed(*s.humidity_mpercent, 1000, 2));
    if (s.pressure_milli_pa) add_number(out, "pressure_hpa", fixed(*s.pressure_milli_pa, 100'000, 2));
    if (s.co2_ppm) add_number(out, "co2_ppm", std::to_string(*s.co2_ppm));
    if (s.co2_age_s) add_number(out, "co2_age_s", std::to_string(*s.co2_age_s));
    if (s.voc_index) add_number(out, "voc_index", std::to_string(*s.voc_index));
    if (s.nox_index) add_number(out, "nox_index", std::to_string(*s.nox_index));
    if (meta.rssi_dbm) add_number(out, "rssi_dbm", std::to_string(*meta.rssi_dbm));
    add_number(out, "uptime_s", std::to_string(meta.uptime_s));
    out += '}';
    return out;
}

std::vector<Message> discovery_messages(const DiscoveryInfo &info)
{
    const std::string id(info.device_id);
    const std::string state = state_topic(info.base_topic, info.device_id);
    const std::string status = status_topic(info.base_topic, info.device_id);

    std::string device = "\"device\":{\"identifiers\":[\"" + json_escape(id) + "\"],\"name\":\"" +
                         json_escape(info.device_name) + "\",\"manufacturer\":\"ClimaSense\",\"model\":\"ClimaSense\"," +
                         "\"sw_version\":\"" + json_escape(info.firmware_version) + "\"}";

    std::vector<Message> messages;
    for (const ValueInfo &v : kValues) {
        std::string p = "{";
        p += "\"name\":\"" + std::string(v.name) + "\"";
        p += ",\"unique_id\":\"" + json_escape(id) + "_" + v.field + "\"";
        p += ",\"state_topic\":\"" + json_escape(state) + "\"";
        p += ",\"value_template\":\"{{ value_json." + std::string(v.field) + " }}\"";
        if (v.unit != nullptr) p += ",\"unit_of_measurement\":\"" + std::string(v.unit) + "\"";
        if (v.device_class != nullptr) p += ",\"device_class\":\"" + std::string(v.device_class) + "\"";
        p += ",\"state_class\":\"measurement\"";
        if (v.diagnostic) p += ",\"entity_category\":\"diagnostic\"";
        p += ",\"availability_topic\":\"" + json_escape(status) + "\"";
        p += ",\"payload_available\":\"online\",\"payload_not_available\":\"offline\"";
        p += "," + device + "}";
        messages.push_back({std::string(info.prefix) + "/sensor/" + id + "/" + v.field + "/config", std::move(p)});
    }
    return messages;
}

}  // namespace telemetry
