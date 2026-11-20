// The decisions around updates: versions, the MQTT command, the image's version, and the trial
// after an update. Pure, tested on the PC.
#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>

namespace ota {

// --- Versions --------------------------------------------------------------------------------

struct Version {
    uint32_t major = 0;
    uint32_t minor = 0;
    uint32_t patch = 0;
    auto operator<=>(const Version &) const = default;
};

// "1.2.3" (exactly three numbers; a leading "v" is allowed). Nothing for anything else.
std::optional<Version> parse_version(std::string_view text);

enum class VersionCheck : uint8_t {
    Newer,       // install
    Same,        // install: a rebuild of the same version (development)
    Older,       // refuse, unless forced
    Unknown,     // a version that is not x.y.z: refuse, unless forced
};

VersionCheck check_version(std::string_view running, std::string_view candidate);

// True if an image with this check may be installed.
constexpr bool allowed(VersionCheck check, bool force)
{
    return force || check == VersionCheck::Newer || check == VersionCheck::Same;
}

// --- The MQTT command ------------------------------------------------------------------------

struct UpdateCommand {
    std::string url;
    bool force = false;  // install even an older version
};

// "<url>" or "<url> force", the URL starting with http:// or https://. Nothing otherwise.
std::optional<UpdateCommand> parse_update_command(std::string_view payload);

// --- The image ---------------------------------------------------------------------------------

// The start of an image holds its version (after the 24-byte image header and the first 8-byte
// segment header comes the app description: magic word 0xABCD5432, then at offset 16 the version).
inline constexpr std::size_t kImageVersionOffset = 24 + 8 + 16;
inline constexpr std::size_t kImageHeadBytes = kImageVersionOffset + 32;

// The version from the first kImageHeadBytes of an image, or nothing if it is not an ESP image.
std::optional<std::string> image_version(std::span<const uint8_t> head);

// --- The trial after an update -----------------------------------------------------------------

// A new firmware runs on trial: it is accepted once it has been healthy (connected to what it is
// configured to connect to) after at least kMinTrialS, and rejected (back to the old firmware) if
// that has not happened within kMaxTrialS. Called once a second.
class TrialGuard {
public:
    static constexpr uint32_t kMinTrialS = 3 * 60;
    static constexpr uint32_t kMaxTrialS = 10 * 60;

    enum class Verdict : uint8_t { Wait, Accept, Reject };

    Verdict check(uint32_t uptime_s, bool healthy) const
    {
        if (healthy && uptime_s >= kMinTrialS) {
            return Verdict::Accept;
        }
        return uptime_s >= kMaxTrialS ? Verdict::Reject : Verdict::Wait;
    }
};

// What "healthy" means for a firmware on trial, from what is configured: the MQTT connection if a
// broker is set, else the Wi-Fi connection if a network is set, else nothing to check.
constexpr bool trial_healthy(bool mqtt_configured, bool mqtt_connected, bool wifi_configured, bool wifi_connected)
{
    if (mqtt_configured) {
        return mqtt_connected;
    }
    if (wifi_configured) {
        return wifi_connected;
    }
    return true;
}

// --- Status messages -------------------------------------------------------------------------------

// {"state":"downloading","progress":40} and the like, for <base>/<id>/ota.
std::string status_json(std::string_view state, std::optional<int> progress = std::nullopt,
                        std::string_view detail = {});

}  // namespace ota
