// The captive portal: setup mode with its own open Wi-Fi network, a DNS responder that points
// every name at the device, and a web page for all settings (docs/decisions.md, "Captive
// portal"). Opens only when no network is configured or on a long press of the BOOT button;
// closes after 10 minutes, on a short press, or by restarting after the settings were saved.
#pragma once

#include "esp_err.h"

#include "net/settings.h"
#include "settings/device.h"
#include "settings/kv_store.h"

namespace portal {

inline constexpr uint32_t kOpenMinutes = 10;

struct Context {
    settings::KvStore *store = nullptr;  // where saved settings go; must outlive the portal
    net::NetSettings net;                // the settings in use, shown and edited on the page
    settings::DeviceSettings device;
    const char *firmware_version = "";
    const char *build_id = "";
};

// Opens setup mode, or, if it is open already, starts its 10 minutes again. Needs Wi-Fi started
// (net::start). Scans for networks first, so the list is ready when the page is opened.
esp_err_t open(const Context &context);

void close();

bool is_open();

}  // namespace portal
