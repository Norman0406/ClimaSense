#include "portal/form.h"

#include <algorithm>

#include "settings/store.h"

namespace portal {

namespace {

int hex_value(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

std::string_view net_field(net::SettingProblem problem)
{
    switch (problem) {
    case net::SettingProblem::PasswordLength:
    case net::SettingProblem::PasswordCharacters: return field::kPassword;
    case net::SettingProblem::CountryCode:        return field::kCountry;
    case net::SettingProblem::SntpServerEmpty:    return field::kSntpServer;
    case net::SettingProblem::TimezoneEmpty:      return field::kTimezone;
    }
    return field::kSsid;
}

std::string_view mqtt_field(telemetry::MqttProblem problem)
{
    switch (problem) {
    case telemetry::MqttProblem::HostCharacters:      return field::kMqttHost;
    case telemetry::MqttProblem::Port:                return field::kMqttPort;
    case telemetry::MqttProblem::PasswordWithoutUser: return field::kMqttPassword;
    case telemetry::MqttProblem::BaseTopic:           return field::kMqttTopic;
    case telemetry::MqttProblem::HaPrefix:            return field::kHaPrefix;
    }
    return field::kMqttHost;
}

// Sets a text field from the form; records an error if the value is malformed or too long.
template <std::size_t N>
void take(std::string_view body, std::string_view key, net::Text<N> &target, std::vector<FieldError> &errors)
{
    FormValue v = form_value(body, key);
    if (v.status == FieldStatus::Missing) {
        return;
    }
    if (v.status == FieldStatus::Malformed) {
        errors.push_back({key, "could not be read; please enter it again"});
        return;
    }
    if (!target.set(v.value)) {
        errors.push_back({key, "is too long (at most " + std::to_string(N) + " bytes)"});
    }
}

}  // namespace

std::optional<std::string> url_decode(std::string_view text)
{
    std::string out;
    out.reserve(text.size());
    for (std::size_t i = 0; i < text.size(); ++i) {
        const char c = text[i];
        if (c == '+') {
            out.push_back(' ');
        } else if (c == '%') {
            if (i + 2 >= text.size()) {
                return std::nullopt;  // "%" or "%X" at the end: the two hex digits are missing
            }
            const int hi = hex_value(text[i + 1]);
            const int lo = hex_value(text[i + 2]);
            if (hi < 0 || lo < 0) {
                return std::nullopt;
            }
            out.push_back(static_cast<char>((hi << 4) | lo));
            i += 2;
        } else {
            out.push_back(c);
        }
    }
    return out;
}

FormValue form_value(std::string_view body, std::string_view key)
{
    while (!body.empty()) {
        const std::size_t amp = body.find('&');
        const std::string_view pair = body.substr(0, amp);
        body = amp == std::string_view::npos ? std::string_view{} : body.substr(amp + 1);

        const std::size_t eq = pair.find('=');
        const auto decoded_key = url_decode(pair.substr(0, eq));
        if (!decoded_key || *decoded_key != key) {
            continue;
        }
        const std::string_view raw = eq == std::string_view::npos ? std::string_view{} : pair.substr(eq + 1);
        auto value = url_decode(raw);
        if (!value) {
            return {FieldStatus::Malformed, {}};
        }
        return {FieldStatus::Present, std::move(*value)};
    }
    return {};
}

FormResult apply_form(std::string_view body, const net::NetSettings &current_net,
                      const settings::DeviceSettings &current_device,
                      const telemetry::MqttSettings &current_mqtt)
{
    FormResult r{current_net, current_device, current_mqtt, {}};

    take(body, field::kSsid, r.net.ssid, r.errors);
    take(body, field::kName, r.device.name, r.errors);
    take(body, field::kSntpServer, r.net.sntp_server, r.errors);
    take(body, field::kTimezone, r.net.timezone, r.errors);

    // Country: accepted in any case, stored in upper case.
    FormValue country = form_value(body, field::kCountry);
    if (country.status == FieldStatus::Malformed) {
        r.errors.push_back({field::kCountry, "could not be read; please enter it again"});
    } else if (country.status == FieldStatus::Present) {
        std::transform(country.value.begin(), country.value.end(), country.value.begin(),
                       [](char c) { return (c >= 'a' && c <= 'z') ? static_cast<char>(c - 'a' + 'A') : c; });
        if (!r.net.country.set(country.value)) {
            r.errors.push_back({field::kCountry, "must be two capital letters, e.g. CH"});
        }
    }

    // Password.
    const bool open_network = form_value(body, field::kOpenNetwork).status == FieldStatus::Present;
    FormValue password = form_value(body, field::kPassword);
    const bool ssid_changed = r.net.ssid.view() != current_net.ssid.view();
    if (password.status == FieldStatus::Malformed) {
        r.errors.push_back({field::kPassword, "could not be read; please enter it again"});
    } else if (open_network && !password.value.empty()) {
        r.errors.push_back({field::kPassword, "either enter a password or tick \"open network\", not both"});
    } else if (open_network) {
        r.net.password.set("");
    } else if (!password.value.empty()) {
        if (!r.net.password.set(password.value)) {
            r.errors.push_back({field::kPassword, "is too long (at most 64 characters)"});
        }
    } else if (ssid_changed && !r.net.ssid.empty()) {
        r.errors.push_back({field::kPassword, "enter the password of the new network, or tick \"open network\""});
    }  // else: empty, same network: the stored password stays

    // MQTT
    take(body, field::kMqttHost, r.mqtt.host, r.errors);
    take(body, field::kMqttUser, r.mqtt.username, r.errors);
    take(body, field::kMqttTopic, r.mqtt.base_topic, r.errors);
    take(body, field::kHaPrefix, r.mqtt.ha_prefix, r.errors);
    FormValue port = form_value(body, field::kMqttPort);
    if (port.status == FieldStatus::Malformed) {
        r.errors.push_back({field::kMqttPort, "could not be read; please enter it again"});
    } else if (port.status == FieldStatus::Present) {
        if (const auto parsed = settings::parse_port(port.value)) {
            r.mqtt.port = *parsed;
        } else {
            r.errors.push_back({field::kMqttPort, "must be a number between 1 and 65535"});
        }
    }
    const bool mqtt_no_password = form_value(body, field::kMqttNoPassword).status == FieldStatus::Present;
    FormValue mqtt_password = form_value(body, field::kMqttPassword);
    if (mqtt_password.status == FieldStatus::Malformed) {
        r.errors.push_back({field::kMqttPassword, "could not be read; please enter it again"});
    } else if (mqtt_no_password && !mqtt_password.value.empty()) {
        r.errors.push_back({field::kMqttPassword, "either enter a password or tick \"no password\", not both"});
    } else if (mqtt_no_password || r.mqtt.username.empty()) {
        r.mqtt.password.set("");
    } else if (!mqtt_password.value.empty() && !r.mqtt.password.set(mqtt_password.value)) {
        r.errors.push_back({field::kMqttPassword, "is too long (at most 63 bytes)"});
    }  // else: empty: the stored password stays
    if (form_value(body, field::kMqttSection).status == FieldStatus::Present) {
        r.mqtt.ha_discovery = form_value(body, field::kHaDiscovery).status == FieldStatus::Present;
    }

    if (r.errors.empty()) {
        if (const auto problem = telemetry::validate(r.mqtt)) {
            r.errors.push_back({mqtt_field(*problem), telemetry::to_string(*problem)});
        }
        if (const auto problem = net::validate(r.net)) {
            r.errors.push_back({net_field(*problem), net::to_string(*problem)});
        }
        if (const auto problem = settings::validate(r.device)) {
            r.errors.push_back({field::kName, settings::to_string(*problem)});
        }
    }
    return r;
}

}  // namespace portal
