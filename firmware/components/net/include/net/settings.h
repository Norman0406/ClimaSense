// Network settings as one record, and the rules for valid values. Pure, no ESP-IDF
// dependencies, tested on the PC.
//
// The Wi-Fi code only ever gets a NetSettings. Today it is filled from the build defaults
// (Kconfig, net/wifi.h: default_settings()); from step 7 on the captive portal stores
// values in NVS that take precedence, and checks them with validate() before saving. Fixed
// sizes, no heap: the limits are those of the Wi-Fi driver.
#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace net {

// A string of at most N bytes, always NUL-terminated.
template <std::size_t N>
class Text {
public:
    static constexpr std::size_t kMaxLength = N;

    Text() = default;
    // An initial value; one longer than N leaves the text empty.
    explicit Text(std::string_view value) { set(value); }

    // False (and unchanged) if `value` is longer than N.
    bool set(std::string_view value)
    {
        if (value.size() > N) {
            return false;
        }
        std::fill(chars_.begin(), chars_.end(), '\0');
        std::copy(value.begin(), value.end(), chars_.begin());
        return true;
    }

    std::string_view view() const
    {
        return {chars_.data(), static_cast<std::size_t>(std::find(chars_.begin(), chars_.end(), '\0') - chars_.begin())};
    }
    const char *c_str() const { return chars_.data(); }
    bool empty() const { return chars_[0] == '\0'; }

private:
    std::array<char, N + 1> chars_{};
};

struct NetSettings {
    Text<32> ssid;          // empty: no network configured, Wi-Fi stays off
    Text<64> password;      // empty: open network
    Text<2> country;        // e.g. "CH"
    Text<63> sntp_server;
    Text<63> timezone;      // POSIX TZ string
};

enum class SettingProblem : uint8_t {
    PasswordLength,   // a WPA password is 8..63 characters, or 64 hex digits
    PasswordCharacters,
    CountryCode,      // two capital letters
    SntpServerEmpty,
    TimezoneEmpty,
};

constexpr const char *to_string(SettingProblem problem)
{
    switch (problem) {
    case SettingProblem::PasswordLength:     return "the password must have 8 to 63 characters (or 64 hex digits)";
    case SettingProblem::PasswordCharacters: return "the password may only contain printable ASCII characters";
    case SettingProblem::CountryCode:        return "the country code must be two capital letters";
    case SettingProblem::SntpServerEmpty:    return "a time server is needed";
    case SettingProblem::TimezoneEmpty:      return "a time zone is needed";
    }
    return "?";
}

// The first problem found, or nothing if the settings can be used. An empty SSID is valid:
// it means "not configured".
std::optional<SettingProblem> validate(const NetSettings &settings);

inline bool wifi_configured(const NetSettings &settings) { return !settings.ssid.empty(); }

}  // namespace net
