// Crash and log diagnostics: build fingerprint, the last log lines before a reset, and the core
// dump of the last crash (docs/firmware/architecture.md, "Debugging").
#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "esp_err.h"
#include "esp_system.h"

#include "diagnostics/log_line.h"

namespace diagnostics {

// Call first thing in app_main, before anything logs. Takes over the log lines kept from before
// the reset (if the reset kept them), clears the buffer and starts recording into it.
void init();

// Logs what is known about the previous run: its last log lines and, if the coredump
// partition holds one, a summary of the crash. Call once after the start-up banner.
void report_previous_boot();

// 16 hex characters of this build's ELF SHA-256. A core dump records the same characters for
// the build that crashed; only that build's .elf decodes it.
const char *build_id();

// Readable name of a reset reason.
const char *reset_reason_name(esp_reset_reason_t reason);

// The log lines from before the last reset; empty after a power-on (step 6 publishes them).
std::string_view previous_log();

// True if the coredump partition holds a valid core dump.
bool has_crash_dump();

// The core dump's summary, if the coredump partition holds one.
struct CrashSummary {
    std::string reason;  // panic reason, e.g. "assert failed"
    std::string task;
    uint32_t pc = 0;
    uint32_t mcause = 0;
    uint32_t mtval = 0;
    uint32_t ra = 0;
    uint32_t sp = 0;
    std::string build;           // fingerprint of the build that crashed
    bool this_build = false;     // the running build is the one that crashed
    bool from_this_reset = false;// the last reset was a crash (else the dump is older)
};
std::optional<CrashSummary> crash_summary();

// --- Log lines for MQTT ---
// Lines at `level` and more severe are queued for sending (WARNING by default; None stops it).
// Lines from the MQTT code itself are never queued, so a broken connection cannot feed itself.
// The queue holds 16 lines; when full, new lines are dropped and counted.
void set_forward_level(LogLevel level);
LogLevel forward_level();
// The oldest queued line, if any, and the number of lines dropped since the last call.
std::optional<std::string> next_forwarded_line();
uint32_t take_dropped_forward_lines();

// Erases the core dump, once it has been reported (step 6: after publishing it over MQTT).
// Until then it stays in flash, and `idf.py coredump-info` can read it over USB.
esp_err_t erase_crash_dump();

}  // namespace diagnostics
