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

std::string boot_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/boot";
}

std::string log_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/log";
}

std::string log_level_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/set/log_level";
}

std::string update_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/set/ota";
}

std::string update_status_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/ota";
}

std::string sanitize_utf8(std::string_view text)
{
    std::string out;
    out.reserve(text.size());
    std::size_t i = 0;
    while (i < text.size()) {
        const auto c = static_cast<unsigned char>(text[i]);
        std::size_t extra = 0;
        uint32_t code = 0;
        if (c < 0x80) {
            out.push_back(text[i++]);
            continue;
        } else if ((c & 0xE0) == 0xC0) {
            extra = 1;
            code = c & 0x1F;
        } else if ((c & 0xF0) == 0xE0) {
            extra = 2;
            code = c & 0x0F;
        } else if ((c & 0xF8) == 0xF0) {
            extra = 3;
            code = c & 0x07;
        } else {
            out.push_back('?');
            ++i;
            continue;
        }
        bool ok = i + extra < text.size();
        for (std::size_t k = 1; ok && k <= extra; ++k) {
            const auto cc = static_cast<unsigned char>(text[i + k]);
            ok = (cc & 0xC0) == 0x80;
            code = (code << 6) | (cc & 0x3F);
        }
        static constexpr uint32_t kMin[] = {0, 0x80, 0x800, 0x10000};
        ok = ok && code >= kMin[extra] && code <= 0x10FFFF && !(code >= 0xD800 && code <= 0xDFFF);
        if (ok) {
            out.append(text.substr(i, extra + 1));
            i += extra + 1;
        } else {
            out.push_back('?');
            ++i;  // resynchronise on the next byte
        }
    }
    return out;
}

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

std::string ble_topic(std::string_view base_topic, std::string_view device_id)
{
    return std::string(base_topic) + "/" + std::string(device_id) + "/ble";
}

std::string ble_json(const ble::Report &report, const BleMeta &meta)
{
    static constexpr char kHex[] = "0123456789abcdef";
    const auto add_hex = [](std::string &out, std::span<const uint8_t> bytes) {
        for (const uint8_t b : bytes) {
            out += kHex[b >> 4];
            out += kHex[b & 0x0F];
        }
    };
    std::string out = "{";
    out.reserve(160 + report.count * 112);
    add_string(out, "id", meta.device_id, true);
    if (!meta.time.empty()) {
        add_string(out, "time", meta.time);
    }
    add_number(out, "window_s", std::to_string(report.window_s));
    if (report.dropped > 0) {
        add_number(out, "dropped", std::to_string(report.dropped));
    }
    out += ",\"fhn\":[";
    for (std::size_t i = 0; i < report.count; ++i) {
        const ble::Sighting &s = report.heard[i];
        out += i == 0 ? "{\"eid\":\"" : ",{\"eid\":\"";
        add_hex(out, s.eid_bytes());
        out += '"';
        add_number(out, "type", std::to_string(s.type));
        if (s.flags) {
            out += ",\"flags\":\"";
            add_hex(out, std::span<const uint8_t>(&*s.flags, 1));
            out += '"';
        }
        if (s.rssi != ble::kRssiUnknown) {
            add_number(out, "rssi", std::to_string(s.rssi));
        }
        add_number(out, "count", std::to_string(s.count));
        add_number(out, "age_s", std::to_string(meta.now_s - s.last_s));
        out += '}';
    }
    out += "]}";
    return out;
}

namespace {

std::string hex32(uint32_t value)
{
    char text[11];
    snprintf(text, sizeof(text), "0x%08lx", static_cast<unsigned long>(value));
    return text;
}

}  // namespace

std::string boot_json(const BootInfo &info)
{
    std::string out = "{";
    add_string(out, "id", info.device_id, true);
    add_string(out, "name", info.name);
    add_string(out, "firmware", info.firmware_version);
    add_string(out, "build", info.build_id);
    add_string(out, "reset_reason", info.reset_reason);
    if (info.on_trial) {
        out += ",\"on_trial\":true";
    }
    if (info.crash) {
        const CrashInfo &c = *info.crash;
        out += ",\"crash\":{";
        add_string(out, "reason", sanitize_utf8(c.reason), true);
        add_string(out, "task", sanitize_utf8(c.task));
        add_string(out, "pc", hex32(c.pc));
        add_string(out, "mcause", hex32(c.mcause));
        add_string(out, "mtval", hex32(c.mtval));
        add_string(out, "ra", hex32(c.ra));
        add_string(out, "sp", hex32(c.sp));
        add_string(out, "build", sanitize_utf8(c.build));
        out += c.this_build ? ",\"this_build\":true" : ",\"this_build\":false";
        out += c.from_this_reset ? ",\"from_this_reset\":true" : ",\"from_this_reset\":false";
        out += '}';
    }
    if (!info.previous_log.empty()) {
        add_string(out, "previous_log", sanitize_utf8(info.previous_log));
    }
    out += '}';
    return out;
}

std::string log_json(std::string_view line)
{
    const auto parsed = diagnostics::parse_log_line(line);
    std::string out = "{";
    if (!parsed) {
        std::string_view text = line;
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) {
            text.remove_suffix(1);
        }
        add_string(out, "msg", sanitize_utf8(text), true);
        out += '}';
        return out;
    }
    const char level[2] = {diagnostics::level_letter(parsed->level), '\0'};
    add_string(out, "level", level, true);
    add_string(out, "tag", sanitize_utf8(parsed->tag));
    add_number(out, "t_ms", std::to_string(parsed->time_ms));
    add_string(out, "msg", sanitize_utf8(parsed->message));
    out += '}';
    return out;
}

std::string dropped_log_json(uint32_t count)
{
    return "{\"level\":\"W\",\"tag\":\"climasense\",\"msg\":\"" + std::to_string(count) +
           " log line(s) not sent (rate limit or full queue)\",\"dropped\":" + std::to_string(count) + "}";
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
