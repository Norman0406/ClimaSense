// Network host name of a board, from its Wi-Fi MAC address: "climasense-" and the last three
// bytes in hex, e.g. "climasense-a1b2c3", so every board is easy to tell apart in the router.
// Pure, tested on the PC.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>

namespace net {

inline constexpr char kHostnamePrefix[] = "climasense-";

using Hostname = std::array<char, sizeof(kHostnamePrefix) - 1 + 6 + 1>;  // prefix, 6 hex, NUL

constexpr Hostname hostname_from_mac(std::span<const uint8_t, 6> mac)
{
    constexpr char kHex[] = "0123456789abcdef";
    Hostname name{};
    std::size_t i = 0;
    for (const char c : std::string_view(kHostnamePrefix)) {
        name[i++] = c;
    }
    for (std::size_t b = 3; b < 6; ++b) {
        name[i++] = kHex[mac[b] >> 4];
        name[i++] = kHex[mac[b] & 0x0F];
    }
    name[i] = '\0';
    return name;
}

}  // namespace net
