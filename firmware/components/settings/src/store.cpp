#include "settings/store.h"

#include <array>

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
