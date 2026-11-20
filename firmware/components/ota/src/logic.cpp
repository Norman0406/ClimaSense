#include "ota/logic.h"

#include <algorithm>

namespace ota {

namespace {

std::optional<uint32_t> parse_number(std::string_view text)
{
    if (text.empty() || text.size() > 9) {
        return std::nullopt;
    }
    uint32_t value = 0;
    for (const char c : text) {
        if (c < '0' || c > '9') {
            return std::nullopt;
        }
        value = value * 10 + static_cast<uint32_t>(c - '0');
    }
    return value;
}

std::string escape(std::string_view text)
{
    std::string out;
    for (const char c : text) {
        if (c == '"' || c == '\\') {
            out.push_back('\\');
            out.push_back(c);
        } else if (static_cast<unsigned char>(c) >= 0x20) {
            out.push_back(c);
        }
    }
    return out;
}

}  // namespace

std::optional<Version> parse_version(std::string_view text)
{
    if (!text.empty() && (text.front() == 'v' || text.front() == 'V')) {
        text.remove_prefix(1);
    }
    // Build metadata after '+' (the commit hash of a release, "0.2.0+1a2b3c4") does not count.
    if (const std::size_t plus = text.find('+'); plus != std::string_view::npos) {
        if (plus + 1 == text.size()) {
            return std::nullopt;  // "1.2.3+" with nothing after it
        }
        text = text.substr(0, plus);
    }
    const std::size_t a = text.find('.');
    if (a == std::string_view::npos) {
        return std::nullopt;
    }
    const std::size_t b = text.find('.', a + 1);
    if (b == std::string_view::npos) {
        return std::nullopt;
    }
    const auto major = parse_number(text.substr(0, a));
    const auto minor = parse_number(text.substr(a + 1, b - a - 1));
    const auto patch = parse_number(text.substr(b + 1));
    if (!major || !minor || !patch) {
        return std::nullopt;
    }
    return Version{*major, *minor, *patch};
}

VersionCheck check_version(std::string_view running, std::string_view candidate)
{
    const auto r = parse_version(running);
    const auto c = parse_version(candidate);
    if (!c) {
        return VersionCheck::Unknown;
    }
    if (!r) {
        return VersionCheck::Newer;  // the running one is not comparable: nothing to protect
    }
    if (*c > *r) return VersionCheck::Newer;
    if (*c == *r) return VersionCheck::Same;
    return VersionCheck::Older;
}

std::optional<UpdateCommand> parse_update_command(std::string_view payload)
{
    while (!payload.empty() && (payload.back() == ' ' || payload.back() == '\n' || payload.back() == '\r')) {
        payload.remove_suffix(1);
    }
    while (!payload.empty() && payload.front() == ' ') {
        payload.remove_prefix(1);
    }
    UpdateCommand command;
    const std::size_t space = payload.find(' ');
    std::string_view url = payload.substr(0, space);
    if (space != std::string_view::npos) {
        std::string_view rest = payload.substr(space + 1);
        while (!rest.empty() && rest.front() == ' ') {
            rest.remove_prefix(1);
        }
        if (rest != "force") {
            return std::nullopt;
        }
        command.force = true;
    }
    const bool http = url.starts_with("http://") && url.size() > 7;
    const bool https = url.starts_with("https://") && url.size() > 8;
    if (!http && !https) {
        return std::nullopt;
    }
    if (std::any_of(url.begin(), url.end(), [](char c) { return static_cast<unsigned char>(c) <= 0x20; })) {
        return std::nullopt;
    }
    command.url = std::string(url);
    return command;
}

std::optional<std::string> image_version(std::span<const uint8_t> head)
{
    if (head.size() < kImageHeadBytes || head[0] != 0xE9) {
        return std::nullopt;  // 0xE9: the ESP image header's magic byte
    }
    const std::size_t m = kImageVersionOffset - 16;
    const uint32_t magic = static_cast<uint32_t>(head[m]) | (static_cast<uint32_t>(head[m + 1]) << 8) |
                           (static_cast<uint32_t>(head[m + 2]) << 16) | (static_cast<uint32_t>(head[m + 3]) << 24);
    if (magic != 0xABCD5432u) {
        return std::nullopt;
    }
    const auto *text = reinterpret_cast<const char *>(head.data() + kImageVersionOffset);
    std::size_t length = 0;
    while (length < 32 && text[length] != '\0') {
        ++length;
    }
    return std::string(text, length);
}

std::string status_json(std::string_view state, std::optional<int> progress, std::string_view detail)
{
    std::string out = "{\"state\":\"" + escape(state) + "\"";
    if (progress) {
        out += ",\"progress\":" + std::to_string(*progress);
    }
    if (!detail.empty()) {
        out += ",\"detail\":\"" + escape(detail) + "\"";
    }
    out += '}';
    return out;
}

}  // namespace ota
