#include "settings/device.h"

namespace settings {

namespace {

// Well-formed UTF-8: no stray continuation bytes, no truncated or overlong sequences, nothing
// beyond U+10FFFF, no surrogates.
bool is_utf8(std::string_view text)
{
    std::size_t i = 0;
    while (i < text.size()) {
        const auto c = static_cast<unsigned char>(text[i]);
        std::size_t extra = 0;
        uint32_t code = 0;
        if (c < 0x80) {
            ++i;
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
            return false;
        }
        if (i + extra >= text.size()) {
            return false;  // the sequence's last byte (at i + extra) is missing: truncated
        }
        for (std::size_t k = 1; k <= extra; ++k) {
            const auto cc = static_cast<unsigned char>(text[i + k]);
            if ((cc & 0xC0) != 0x80) {
                return false;
            }
            code = (code << 6) | (cc & 0x3F);
        }
        static constexpr uint32_t kMin[] = {0, 0x80, 0x800, 0x10000};
        if (code < kMin[extra] || code > 0x10FFFF || (code >= 0xD800 && code <= 0xDFFF)) {
            return false;
        }
        i += extra + 1;
    }
    return true;
}

}  // namespace

std::optional<DeviceProblem> validate(const DeviceSettings &settings)
{
    const std::string_view name = settings.name.view();
    if (!is_utf8(name)) {
        return DeviceProblem::NameNotUtf8;
    }
    for (const char ch : name) {
        const auto c = static_cast<unsigned char>(ch);
        if (c < 0x20 || c == 0x7F) {
            return DeviceProblem::NameControlCharacters;
        }
    }
    return std::nullopt;
}

}  // namespace settings
