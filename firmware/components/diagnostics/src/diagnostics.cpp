#include "diagnostics/diagnostics.h"

#include <algorithm>
#include <atomic>
#include <cinttypes>
#include <cstdarg>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string_view>

#include "esp_app_desc.h"
#include "esp_attr.h"
#include "esp_core_dump.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

#include "diagnostics/line_queue.h"
#include "diagnostics/log_line.h"
#include "diagnostics/log_ring.h"

namespace diagnostics {

namespace {

constexpr const char *kTag = "diag";
constexpr std::size_t kRingBytes = 2048;
constexpr std::size_t kLineMax = 160;  // longer log lines are kept cut to this length
constexpr std::size_t kBuildIdChars = 16;

RTC_NOINIT_ATTR LogRingStorage<kRingBytes> g_storage;
LogRing<kRingBytes> g_ring{g_storage};
portMUX_TYPE g_lock = portMUX_INITIALIZER_UNLOCKED;
vprintf_like_t g_console = nullptr;

char g_previous[kRingBytes];
std::size_t g_previous_length = 0;

char g_build_id[kBuildIdChars + 1] = {};

esp_core_dump_summary_t g_summary;  // ~1.1 KB, too big for the caller's stack

// Log lines waiting to go out over MQTT; shares g_lock with the ring.
LineQueue<16, kLineMax> g_forward;
std::atomic<uint8_t> g_forward_level{static_cast<uint8_t>(LogLevel::Warn)};

bool forwarded(std::string_view line)
{
    const auto parsed = parse_log_line(line);
    if (!parsed) {
        return false;
    }
    const auto threshold = static_cast<LogLevel>(g_forward_level.load());
    if (threshold == LogLevel::None || parsed->level > threshold) {
        return false;
    }
    // Not the MQTT code's own lines: when the connection is the problem, they cannot be sent,
    // and sending them could log again.
    return parsed->tag != "mqtt" && parsed->tag != "mqtt_client" && parsed->tag != "transport_base";
}

// Every log line passes through here (log format version 1: one call per line). Keeps a copy
// in the ring, then hands the line to the console as before. Called from any task, never from
// an interrupt (ESP_LOGx is not allowed there).
int log_hook(const char *format, va_list args)
{
    char line[kLineMax];
    va_list copy;
    va_copy(copy, args);
    const int n = vsnprintf(line, sizeof(line), format, copy);
    va_end(copy);

    if (n > 0) {
        const std::size_t length = std::min(static_cast<std::size_t>(n), sizeof(line) - 1);
        const bool cut = static_cast<std::size_t>(n) >= sizeof(line);
        const bool forward = forwarded({line, length});
        taskENTER_CRITICAL(&g_lock);
        g_ring.append({line, length});
        if (cut) {
            g_ring.append("\n");  // keep one line per line
        }
        if (forward) {
            g_forward.push({line, length});
        }
        taskEXIT_CRITICAL(&g_lock);
    }
    return g_console != nullptr ? g_console(format, args) : n;
}

bool memory_survived(esp_reset_reason_t reason)
{
    // After a power cut or brownout, RTC memory holds garbage that may even look valid.
    return reason != ESP_RST_POWERON && reason != ESP_RST_BROWNOUT && reason != ESP_RST_PWR_GLITCH &&
           reason != ESP_RST_UNKNOWN;
}

bool is_crash(esp_reset_reason_t reason)
{
    return reason == ESP_RST_PANIC || reason == ESP_RST_INT_WDT || reason == ESP_RST_TASK_WDT ||
           reason == ESP_RST_WDT || reason == ESP_RST_CPU_LOCKUP;
}

void report_core_dump(esp_reset_reason_t reason)
{
    const auto summary = crash_summary();
    if (!summary) {
        if (has_crash_dump()) {
            ESP_LOGE(kTag, "core dump in flash, but its summary cannot be read");
        } else if (is_crash(reason)) {
            ESP_LOGW(kTag, "reset by a crash, but no core dump in flash");
        }
        return;
    }
    ESP_LOGE(kTag, "core dump in flash%s", summary->from_this_reset ? " from this reset" : " from an earlier crash");
    ESP_LOGE(kTag, "  reason: %s", summary->reason.c_str());
    ESP_LOGE(kTag, "  task \"%s\", PC 0x%08" PRIx32, summary->task.c_str(), summary->pc);
    ESP_LOGE(kTag, "  mcause 0x%08" PRIx32 ", mtval 0x%08" PRIx32 ", ra 0x%08" PRIx32 ", sp 0x%08" PRIx32,
             summary->mcause, summary->mtval, summary->ra, summary->sp);
    ESP_LOGE(kTag, "  crashed build %s%s", summary->build.c_str(),
             summary->this_build ? " (this build)" : " (another build)");
    ESP_LOGE(kTag, "  full backtrace: idf.py coredump-info, with that build's .elf");
}

}  // namespace

void init()
{
    const esp_reset_reason_t reason = esp_reset_reason();
    if (memory_survived(reason) && g_ring.valid()) {
        g_previous_length = g_ring.copy_out(g_previous);
    }
    g_ring.clear();
    g_console = esp_log_set_vprintf(log_hook);
}

void report_previous_boot()
{
    const esp_reset_reason_t reason = esp_reset_reason();
    if (g_previous_length > 0) {
        ESP_LOGW(kTag, "last %u bytes of log before the reset (%s):",
                 static_cast<unsigned>(g_previous_length), reset_reason_name(reason));
        // Straight to the console, not through the log: these lines must not go into the ring again.
        fwrite(g_previous, 1, g_previous_length, stdout);
        fflush(stdout);
        ESP_LOGW(kTag, "end of the previous log");
    }
    report_core_dump(reason);
}

const char *build_id()
{
    if (g_build_id[0] == '\0') {
        esp_app_get_elf_sha256(g_build_id, sizeof(g_build_id));
    }
    return g_build_id;
}

const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
    case ESP_RST_POWERON:    return "power-on";
    case ESP_RST_EXT:        return "external pin";
    case ESP_RST_SW:         return "software";
    case ESP_RST_PANIC:      return "panic";
    case ESP_RST_INT_WDT:    return "interrupt watchdog";
    case ESP_RST_TASK_WDT:   return "task watchdog";
    case ESP_RST_WDT:        return "other watchdog";
    case ESP_RST_DEEPSLEEP:  return "deep sleep";
    case ESP_RST_BROWNOUT:   return "brownout";
    case ESP_RST_USB:        return "USB";
    case ESP_RST_JTAG:       return "JTAG";
    case ESP_RST_PWR_GLITCH: return "power glitch";
    case ESP_RST_CPU_LOCKUP: return "CPU lock-up";
    default:                 return "other";
    }
}

std::string_view previous_log() { return {g_previous, g_previous_length}; }

bool has_crash_dump() { return esp_core_dump_image_check() == ESP_OK; }

std::optional<CrashSummary> crash_summary()
{
    if (!has_crash_dump() || esp_core_dump_get_summary(&g_summary) != ESP_OK) {
        return std::nullopt;
    }
    CrashSummary s;
    char panic_reason[96] = "unknown";
    esp_core_dump_get_panic_reason(panic_reason, sizeof(panic_reason));
    s.reason = panic_reason;
    s.task.assign(g_summary.exc_task, strnlen(g_summary.exc_task, sizeof(g_summary.exc_task)));
    s.pc = g_summary.exc_pc;
    s.mcause = g_summary.ex_info.mcause;
    s.mtval = g_summary.ex_info.mtval;
    s.ra = g_summary.ex_info.ra;
    s.sp = g_summary.ex_info.sp;
    const auto *sha = reinterpret_cast<const char *>(g_summary.app_elf_sha256);
    s.build.assign(sha, strnlen(sha, sizeof(g_summary.app_elf_sha256)));
    s.this_build = s.build == build_id();
    s.from_this_reset = is_crash(esp_reset_reason());
    return s;
}

void set_forward_level(LogLevel level) { g_forward_level = static_cast<uint8_t>(level); }

LogLevel forward_level() { return static_cast<LogLevel>(g_forward_level.load()); }

std::optional<std::string> next_forwarded_line()
{
    char line[kLineMax];
    taskENTER_CRITICAL(&g_lock);
    const std::size_t n = g_forward.pop(line);
    taskEXIT_CRITICAL(&g_lock);
    if (n == 0) {
        return std::nullopt;
    }
    return std::string(line, n);
}

uint32_t take_dropped_forward_lines()
{
    taskENTER_CRITICAL(&g_lock);
    const uint32_t dropped = g_forward.take_dropped();
    taskEXIT_CRITICAL(&g_lock);
    return dropped;
}

esp_err_t erase_crash_dump() { return esp_core_dump_image_erase(); }

}  // namespace diagnostics
