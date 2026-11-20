// The portal's HTML pages. Pure, tested on the PC.
//
// Everything that comes from outside (network names from the scan, which anyone nearby can choose,
// and the user's own input) is HTML-escaped. The password is never written into a page.
#pragma once

#include <span>
#include <string>
#include <string_view>

#include "net/networks.h"
#include "net/settings.h"
#include "portal/form.h"
#include "settings/device.h"

namespace portal {

std::string html_escape(std::string_view text);

struct PageModel {
    std::string_view device_id;
    std::string_view firmware_version;
    std::string_view build_id;
    bool wifi_connected = false;
    const net::NetSettings *net = nullptr;          // values to show (the password is not)
    const settings::DeviceSettings *device = nullptr;
    bool password_stored = false;                   // a password is stored for the shown network
    std::span<const net::AccessPoint> networks;
    std::span<const FieldError> errors;
    std::string_view notice;                        // e.g. a storage failure
};

std::string render_settings_page(const PageModel &model);

// After saving: tells the user the device restarts and where to find it.
std::string render_saved_page(std::string_view display_name, std::string_view ssid);

}  // namespace portal
