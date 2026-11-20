// Updates over the air (docs/decisions.md, "Updates"): from a URL named in an MQTT command, or
// uploaded in the setup portal. Only images signed with our key are installed (checked by
// ESP-IDF when the image is finished), and by default only the same or a newer version. A new
// firmware then runs on trial (ota/logic.h, TrialGuard) until app_main accepts or rejects it.
#pragma once

#include <array>
#include <cstdint>
#include <span>
#include <string>

#include "esp_err.h"

#include "ota/logic.h"

namespace ota {

// Where status messages go ({"state":...}, ota/logic.h status_json); may be nullptr.
using StatusFn = bool (*)(const std::string &json);

// Downloads and installs in a task of its own, reporting progress, then restarts. Refused while
// another update runs or the running firmware is still on trial.
esp_err_t start_from_url(const UpdateCommand &command, StatusFn status);

bool busy();

// --- Upload in the setup portal --------------------------------------------------------------

class Upload {
public:
    // Starts writing to the free update slot.
    esp_err_t begin(bool force);
    // The image in pieces, in order. The version is checked once its start has arrived.
    esp_err_t write(std::span<const uint8_t> data);
    // Checks the whole image (including its signature) and makes it the one to boot next.
    esp_err_t finish();
    void abort();

    const std::string &error() const { return error_; }  // why the last call failed, for the page
    const std::string &version() const { return version_; }

private:
    esp_err_t fail(esp_err_t err, std::string why);

    uint32_t handle_ = 0;
    const void *partition_ = nullptr;
    bool open_ = false;
    bool force_ = false;
    bool version_checked_ = false;
    std::array<uint8_t, kImageHeadBytes> head_{};
    std::size_t head_length_ = 0;
    std::string error_;
    std::string version_;
};

// --- The trial after an update -----------------------------------------------------------------

// True while the running firmware is a new one not yet confirmed (rollback pending).
bool on_trial();
// Confirms it: it stays.
void accept();
// Rejects it: marks it invalid and restarts into the previous firmware.
void reject();

}  // namespace ota
