#include "settings/store.h"

#include <array>
#include <cstdio>
#include <string>
#include <string_view>

namespace settings {

namespace {

// Reads one field. Not stored: the default stays. Stored: it replaces the default, even if
// empty. A value too long for the field counts as invalid (`bad`).
template <std::size_t N>
void load_field(KvStore &store, const char *key, net::Text<N> &field, uint8_t &stored, bool &bad, bool &failed)
{
    std::array<char, N + 1> buffer{};
    const auto r = store.get(key, buffer);
    if (r) {
        field.set(std::string_view(buffer.data(), *r));
        ++stored;
    } else if (r.error() == KvError::TooLong) {
        bad = true;
    } else if (r.error() == KvError::Failed) {
        failed = true;
    }
}

// Reads a field stored as text into a small buffer; the parsing is the caller's.
std::optional<std::string> load_raw(KvStore &store, const char *key, uint8_t &stored, bool &bad, bool &failed)
{
    std::array<char, 8> buffer{};
    const auto r = store.get(key, buffer);
    if (r) {
        ++stored;
        return std::string(buffer.data(), *r);
    }
    if (r.error() == KvError::TooLong) {
        bad = true;
    } else if (r.error() == KvError::Failed) {
        failed = true;
    }
    return std::nullopt;
}

template <std::size_t N>
bool save_field(KvStore &store, const char *key, const net::Text<N> &field)
{
    return store.set(key, field.view()).has_value();
}

}  // namespace

Loaded<net::NetSettings> load_net(KvStore &store, const net::NetSettings &defaults)
{
    Loaded<net::NetSettings> result{defaults};
    bool bad = false;
    load_field(store, key::kWifiSsid, result.value.ssid, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kWifiPassword, result.value.password, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kWifiCountry, result.value.country, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kSntpServer, result.value.sntp_server, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kTimezone, result.value.timezone, result.stored_fields, bad, result.store_failed);
    if (bad || net::validate(result.value)) {
        result.value = defaults;
        result.rejected = true;
    }
    return result;
}

Loaded<DeviceSettings> load_device(KvStore &store, const DeviceSettings &defaults)
{
    Loaded<DeviceSettings> result{defaults};
    bool bad = false;
    load_field(store, key::kDeviceName, result.value.name, result.stored_fields, bad, result.store_failed);
    if (bad || validate(result.value)) {
        result.value = defaults;
        result.rejected = true;
    }
    return result;
}

std::optional<uint16_t> parse_port(std::string_view text)
{
    if (text.empty() || text.size() > 5 || text[0] == '0') {
        return std::nullopt;
    }
    uint32_t value = 0;
    for (const char c : text) {
        if (c < '0' || c > '9') {
            return std::nullopt;
        }
        value = value * 10 + static_cast<uint32_t>(c - '0');
    }
    if (value > 65535) {
        return std::nullopt;
    }
    return static_cast<uint16_t>(value);
}

Loaded<telemetry::MqttSettings> load_mqtt(KvStore &store, const telemetry::MqttSettings &defaults)
{
    Loaded<telemetry::MqttSettings> result{defaults};
    bool bad = false;
    auto &v = result.value;
    load_field(store, key::kMqttHost, v.host, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kMqttUser, v.username, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kMqttPassword, v.password, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kMqttBaseTopic, v.base_topic, result.stored_fields, bad, result.store_failed);
    load_field(store, key::kHaPrefix, v.ha_prefix, result.stored_fields, bad, result.store_failed);
    if (const auto port = load_raw(store, key::kMqttPort, result.stored_fields, bad, result.store_failed)) {
        if (const auto parsed = parse_port(*port)) {
            v.port = *parsed;
        } else {
            bad = true;
        }
    }
    if (const auto ha = load_raw(store, key::kHaDiscovery, result.stored_fields, bad, result.store_failed)) {
        if (*ha == "1" || *ha == "0") {
            v.ha_discovery = *ha == "1";
        } else {
            bad = true;
        }
    }
    if (bad || telemetry::validate(v)) {
        result.value = defaults;
        result.rejected = true;
    }
    return result;
}

std::optional<SaveError> save_mqtt(KvStore &store, const telemetry::MqttSettings &settings)
{
    if (telemetry::validate(settings)) {
        return SaveError::Invalid;
    }
    char port[8];
    snprintf(port, sizeof(port), "%u", static_cast<unsigned>(settings.port));
    const bool ok = save_field(store, key::kMqttHost, settings.host) &&
                    store.set(key::kMqttPort, port).has_value() &&
                    save_field(store, key::kMqttUser, settings.username) &&
                    save_field(store, key::kMqttPassword, settings.password) &&
                    save_field(store, key::kMqttBaseTopic, settings.base_topic) &&
                    store.set(key::kHaDiscovery, settings.ha_discovery ? "1" : "0").has_value() &&
                    save_field(store, key::kHaPrefix, settings.ha_prefix) && store.commit().has_value();
    return ok ? std::nullopt : std::optional<SaveError>{SaveError::StoreFailed};
}

std::optional<SaveError> save_net(KvStore &store, const net::NetSettings &settings)
{
    if (net::validate(settings)) {
        return SaveError::Invalid;
    }
    const bool ok = save_field(store, key::kWifiSsid, settings.ssid) &&
                    save_field(store, key::kWifiPassword, settings.password) &&
                    save_field(store, key::kWifiCountry, settings.country) &&
                    save_field(store, key::kSntpServer, settings.sntp_server) &&
                    save_field(store, key::kTimezone, settings.timezone) && store.commit().has_value();
    return ok ? std::nullopt : std::optional<SaveError>{SaveError::StoreFailed};
}

std::optional<SaveError> save_device(KvStore &store, const DeviceSettings &settings)
{
    if (validate(settings)) {
        return SaveError::Invalid;
    }
    const bool ok = save_field(store, key::kDeviceName, settings.name) && store.commit().has_value();
    return ok ? std::nullopt : std::optional<SaveError>{SaveError::StoreFailed};
}

}  // namespace settings
