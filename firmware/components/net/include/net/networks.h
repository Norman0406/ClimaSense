// Nearby Wi-Fi networks, as the portal lists them. Pure, tested on the PC.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace net {

struct AccessPoint {
    std::string ssid;
    int8_t rssi = 0;     // dBm
    bool secure = true;  // needs a password
};

inline constexpr std::size_t kMaxListedNetworks = 20;

// Drops hidden networks (no name), keeps the strongest access point of each name, sorts by signal
// strength (strongest first) and keeps at most kMaxListedNetworks.
inline std::vector<AccessPoint> tidy_networks(std::vector<AccessPoint> found)
{
    std::erase_if(found, [](const AccessPoint &ap) { return ap.ssid.empty(); });
    std::stable_sort(found.begin(), found.end(), [](const AccessPoint &a, const AccessPoint &b) { return a.rssi > b.rssi; });
    std::vector<AccessPoint> result;
    for (auto &ap : found) {
        const bool seen = std::any_of(result.begin(), result.end(), [&](const AccessPoint &r) { return r.ssid == ap.ssid; });
        if (!seen) {
            result.push_back(std::move(ap));
        }
        if (result.size() == kMaxListedNetworks) {
            break;
        }
    }
    return result;
}

}  // namespace net
