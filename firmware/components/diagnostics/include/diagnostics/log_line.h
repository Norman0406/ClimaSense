// ESP-IDF log lines ("W (12345) wifi: disconnected"), taken apart. Pure, tested on the PC.
#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

namespace diagnostics {

// Same order and values as ESP-IDF's esp_log_level_t: a lower value is more severe.
enum class LogLevel : uint8_t { None = 0, Error = 1, Warn = 2, Info = 3, Debug = 4, Verbose = 5 };

struct LogLine {
    LogLevel level;
    uint32_t time_ms;          // milliseconds since boot, as the log prints it
    std::string_view tag;
    std::string_view message;  // without the trailing newline
};

// Parses a line in ESP-IDF's log format (version 1, no colours). Nothing for other text, such as
// the ROM's or the bootloader's output.
std::optional<LogLine> parse_log_line(std::string_view line);

constexpr char level_letter(LogLevel level)
{
    switch (level) {
    case LogLevel::Error:   return 'E';
    case LogLevel::Warn:    return 'W';
    case LogLevel::Info:    return 'I';
    case LogLevel::Debug:   return 'D';
    case LogLevel::Verbose: return 'V';
    case LogLevel::None:    break;
    }
    return '?';
}

// "error", "warn", "info", "debug" or "none" (the remote log level command); nothing otherwise.
std::optional<LogLevel> parse_level_name(std::string_view name);

}  // namespace diagnostics
