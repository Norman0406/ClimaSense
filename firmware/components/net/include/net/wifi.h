// Wi-Fi station and network time.
#pragma once

#include "esp_err.h"

#include "net/settings.h"

namespace net {

// The build defaults (Kconfig "ClimaSense network"). From step 7 on, settings stored by the
// captive portal take precedence over these.
NetSettings default_settings();

// Starts Wi-Fi in station mode with these settings and returns; connecting, reconnecting
// (net/backoff.h) and the network time sync after the first connection happen in the
// background. Needs NVS to be initialised. With no SSID configured it logs that and does
// nothing. Call once; the settings are copied.
esp_err_t start(const NetSettings &settings);

bool connected();
bool time_synced();

}  // namespace net
