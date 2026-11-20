// Wi-Fi station and network time.
#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "esp_err.h"

#include "net/networks.h"
#include "net/settings.h"

namespace net {

// The build defaults (Kconfig "ClimaSense network"). From step 7 on, settings stored by the
// captive portal take precedence over these.
NetSettings default_settings();

// Starts Wi-Fi in station mode with these settings and returns; connecting, reconnecting
// (net/backoff.h) and the network time sync after the first connection happen in the
// background. Needs NVS to be initialised. The radio also starts with no network configured
// (it then connects to nothing), because the setup portal needs it. Call once; the settings
// are copied.
esp_err_t start(const NetSettings &settings);

// This board's fixed ID, also its host name: "climasense-" and the last three bytes of its
// Wi-Fi MAC address (net/hostname.h). Available before start().
const char *device_id();

bool connected();
bool time_synced();

// Setup mode for the portal: adds an open access point with this name next to the station and
// pauses reconnect attempts, so the station does not leave the access point's channel to search.
// Sets `ip` to the access point's address, which DHCP also announces as the portal (option 114).
esp_err_t start_access_point(const char *ssid, std::array<uint8_t, 4> &ip);
void stop_access_point();

// Looks for nearby networks; blocks for about 2-3 s. Tidied (net/networks.h).
std::vector<AccessPoint> scan();

}  // namespace net
