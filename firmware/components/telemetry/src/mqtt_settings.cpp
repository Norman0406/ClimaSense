#include "telemetry/mqtt_settings.h"

#include <algorithm>

namespace telemetry {

namespace {

bool host_char(char c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-';
}

bool topic_char(char c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
}

}  // namespace

bool valid_topic(std::string_view topic)
{
    if (topic.empty()) {
        return false;
    }
    std::size_t level_length = 0;
    for (const char c : topic) {
        if (c == '/') {
            if (level_length == 0) {
                return false;  // leading or double '/'
            }
            level_length = 0;
        } else if (topic_char(c)) {
            ++level_length;
        } else {
            return false;
        }
    }
    return level_length > 0;  // no trailing '/'
}

std::optional<MqttProblem> validate(const MqttSettings &settings)
{
    const std::string_view host = settings.host.view();
    if (!std::all_of(host.begin(), host.end(), host_char)) {
        return MqttProblem::HostCharacters;
    }
    if (settings.port == 0) {
        return MqttProblem::Port;
    }
    if (settings.username.empty() && !settings.password.empty()) {
        return MqttProblem::PasswordWithoutUser;
    }
    if (!valid_topic(settings.base_topic.view())) {
        return MqttProblem::BaseTopic;
    }
    if (!valid_topic(settings.ha_prefix.view())) {
        return MqttProblem::HaPrefix;
    }
    return std::nullopt;
}

}  // namespace telemetry
