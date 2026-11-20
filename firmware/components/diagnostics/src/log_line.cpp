#include "diagnostics/log_line.h"

namespace diagnostics {

std::optional<LogLine> parse_log_line(std::string_view line)
{
    // <letter> " (" <digits> ") " <tag> ": " <message> ["\n"]
    if (line.size() < 6 || line[1] != ' ' || line[2] != '(') {
        return std::nullopt;
    }
    LogLevel level;
    switch (line[0]) {
    case 'E': level = LogLevel::Error; break;
    case 'W': level = LogLevel::Warn; break;
    case 'I': level = LogLevel::Info; break;
    case 'D': level = LogLevel::Debug; break;
    case 'V': level = LogLevel::Verbose; break;
    default:  return std::nullopt;
    }
    std::size_t i = 3;
    uint64_t time = 0;
    const std::size_t digits_start = i;
    while (i < line.size() && line[i] >= '0' && line[i] <= '9') {
        time = time * 10 + static_cast<uint64_t>(line[i] - '0');
        ++i;
    }
    if (i == digits_start || i + 1 >= line.size() || line[i] != ')' || line[i + 1] != ' ') {
        return std::nullopt;
    }
    i += 2;
    const std::size_t colon = line.find(": ", i);
    if (colon == std::string_view::npos || colon == i) {
        return std::nullopt;
    }
    std::string_view message = line.substr(colon + 2);
    while (!message.empty() && (message.back() == '\n' || message.back() == '\r')) {
        message.remove_suffix(1);
    }
    return LogLine{level, static_cast<uint32_t>(time), line.substr(i, colon - i), message};
}

std::optional<LogLevel> parse_level_name(std::string_view name)
{
    if (name == "none") return LogLevel::None;
    if (name == "error") return LogLevel::Error;
    if (name == "warn") return LogLevel::Warn;
    if (name == "info") return LogLevel::Info;
    if (name == "debug") return LogLevel::Debug;
    return std::nullopt;
}

}  // namespace diagnostics
