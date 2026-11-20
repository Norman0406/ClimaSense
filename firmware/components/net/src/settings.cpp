#include "net/settings.h"

namespace net {

namespace {

bool is_hex(char c)
{
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

bool is_printable_ascii(char c) { return c >= 0x20 && c <= 0x7E; }

}  // namespace

std::optional<SettingProblem> validate(const NetSettings &settings)
{
    const std::string_view password = settings.password.view();
    if (!password.empty()) {
        if (password.size() == 64) {
            // A raw 256-bit key, written as 64 hex digits.
            if (!std::all_of(password.begin(), password.end(), is_hex)) {
                return SettingProblem::PasswordLength;
            }
        } else if (password.size() < 8 || password.size() > 63) {
            return SettingProblem::PasswordLength;
        } else if (!std::all_of(password.begin(), password.end(), is_printable_ascii)) {
            return SettingProblem::PasswordCharacters;
        }
    }

    const std::string_view country = settings.country.view();
    if (country.size() != 2 || !std::all_of(country.begin(), country.end(), [](char c) { return c >= 'A' && c <= 'Z'; })) {
        return SettingProblem::CountryCode;
    }
    if (settings.sntp_server.empty()) {
        return SettingProblem::SntpServerEmpty;
    }
    if (settings.timezone.empty()) {
        return SettingProblem::TimezoneEmpty;
    }
    return std::nullopt;
}

}  // namespace net
