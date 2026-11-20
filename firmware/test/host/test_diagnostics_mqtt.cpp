#include <array>
#include <cstdint>
#include <string>
#include <string_view>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "diagnostics/line_queue.h"
#include "diagnostics/log_line.h"
#include "telemetry/payload.h"
#include "telemetry/rate_limit.h"

using diagnostics::LogLevel;
using ::testing::HasSubstr;
using ::testing::Not;

// --- Log line parsing --------------------------------------------------------------------------

TEST(LogLine, ParsesEspIdfLines)
{
    const auto l = diagnostics::parse_log_line("W (12345) wifi: disconnected (reason 201)\n");
    ASSERT_TRUE(l);
    EXPECT_EQ(l->level, LogLevel::Warn);
    EXPECT_EQ(l->time_ms, 12345u);
    EXPECT_EQ(l->tag, "wifi");
    EXPECT_EQ(l->message, "disconnected (reason 201)");

    const auto e = diagnostics::parse_log_line("E (7) diag: core dump in flash: from this reset");
    ASSERT_TRUE(e);
    EXPECT_EQ(e->level, LogLevel::Error);
    EXPECT_EQ(e->tag, "diag");
    EXPECT_EQ(e->message, "core dump in flash: from this reset");  // first ": " ends the tag
}

TEST(LogLine, RejectsOtherText)
{
    for (const char *bad : {"", "hello", "X (1) tag: m", "W 12 tag: m", "W () tag: m", "W (12)tag: m", "W (12) tag",
                            "W (12) : no tag", "ESP-ROM:esp32c6-20220919"}) {
        EXPECT_FALSE(diagnostics::parse_log_line(bad)) << bad;
    }
}

TEST(LogLine, LevelNames)
{
    EXPECT_EQ(diagnostics::parse_level_name("warn"), LogLevel::Warn);
    EXPECT_EQ(diagnostics::parse_level_name("debug"), LogLevel::Debug);
    EXPECT_EQ(diagnostics::parse_level_name("none"), LogLevel::None);
    EXPECT_FALSE(diagnostics::parse_level_name("WARN"));
    EXPECT_FALSE(diagnostics::parse_level_name("verbose"));
    EXPECT_EQ(diagnostics::level_letter(LogLevel::Info), 'I');
}

// --- Line queue ----------------------------------------------------------------------------------

TEST(LineQueue, FirstInFirstOutAndCutsLongLines)
{
    diagnostics::LineQueue<3, 8> q;
    q.push("one");
    q.push("a very long line");
    std::array<char, 16> out{};
    EXPECT_EQ(std::string(out.data(), q.pop(out)), "one");
    EXPECT_EQ(std::string(out.data(), q.pop(out)), "a very l");  // cut to 8 bytes
    EXPECT_EQ(q.pop(out), 0u);
}

TEST(LineQueue, WhenFullKeepsTheOldLinesAndCountsTheDropped)
{
    diagnostics::LineQueue<2, 16> q;
    q.push("cause");
    q.push("effect");
    q.push("dropped 1");
    q.push("dropped 2");
    EXPECT_EQ(q.size(), 2u);
    EXPECT_EQ(q.take_dropped(), 2u);
    EXPECT_EQ(q.take_dropped(), 0u);
    std::array<char, 16> out{};
    EXPECT_EQ(std::string(out.data(), q.pop(out)), "cause");
    q.push("next");  // wraps around
    EXPECT_EQ(std::string(out.data(), q.pop(out)), "effect");
    EXPECT_EQ(std::string(out.data(), q.pop(out)), "next");
}

// --- Rate limit ----------------------------------------------------------------------------------

TEST(RateLimiter, AllowsTenPerMinute)
{
    telemetry::RateLimiter limit(10, 60);
    int allowed = 0;
    for (int i = 0; i < 25; ++i) {
        allowed += limit.allow(100) ? 1 : 0;
    }
    EXPECT_EQ(allowed, 10);
    EXPECT_FALSE(limit.allow(159));
    EXPECT_TRUE(limit.allow(160));  // a new window
}

// --- Messages ------------------------------------------------------------------------------------

TEST(DiagnosticsPayload, SanitizeUtf8)
{
    EXPECT_EQ(telemetry::sanitize_utf8("Küche"), "Küche");
    EXPECT_EQ(telemetry::sanitize_utf8("a\xFF" "b"), "a?b");
    EXPECT_EQ(telemetry::sanitize_utf8("trunc\xC3"), "trunc?");
    EXPECT_EQ(telemetry::sanitize_utf8("\xC0\xAF"), "??");        // overlong: both bytes replaced
    EXPECT_EQ(telemetry::sanitize_utf8("\xED\xA0\x80" "x"), "???x");  // surrogate
}

TEST(DiagnosticsPayload, LogMessage)
{
    EXPECT_EQ(telemetry::log_json("W (12345) wifi: disconnected \"x\"\n"),
              "{\"level\":\"W\",\"tag\":\"wifi\",\"t_ms\":12345,\"msg\":\"disconnected \\\"x\\\"\"}");
    EXPECT_EQ(telemetry::log_json("raw text\n"), "{\"msg\":\"raw text\"}");
    EXPECT_THAT(telemetry::dropped_log_json(7), HasSubstr("\"dropped\":7"));
}

TEST(DiagnosticsPayload, BootReportWithoutCrash)
{
    telemetry::BootInfo info;
    info.device_id = "climasense-a1b2c3";
    info.name = "Living room";
    info.firmware_version = "v1.0";
    info.build_id = "0123456789abcdef";
    info.reset_reason = "power-on";
    EXPECT_EQ(telemetry::boot_json(info),
              "{\"id\":\"climasense-a1b2c3\",\"name\":\"Living room\",\"firmware\":\"v1.0\","
              "\"build\":\"0123456789abcdef\",\"reset_reason\":\"power-on\"}");
}

TEST(DiagnosticsPayload, BootReportWithCrashAndPreviousLog)
{
    telemetry::BootInfo info;
    info.device_id = "id";
    info.name = "n";
    info.firmware_version = "v";
    info.build_id = "b";
    info.reset_reason = "panic";
    info.previous_log = "I (1) a: one\nE (2) b: two\n";
    telemetry::CrashInfo crash;
    crash.reason = "assert failed";
    crash.task = "sensors";
    crash.pc = 0x4200A3C4;
    crash.mcause = 2;
    crash.build = "b";
    crash.this_build = true;
    crash.from_this_reset = true;
    info.crash = crash;
    const std::string json = telemetry::boot_json(info);
    EXPECT_THAT(json, HasSubstr("\"crash\":{\"reason\":\"assert failed\",\"task\":\"sensors\",\"pc\":\"0x4200a3c4\","
                                "\"mcause\":\"0x00000002\""));
    EXPECT_THAT(json, HasSubstr("\"this_build\":true,\"from_this_reset\":true}"));
    EXPECT_THAT(json, HasSubstr("\"previous_log\":\"I (1) a: one\\nE (2) b: two\\n\""));
    EXPECT_EQ(json.back(), '}');
}

TEST(DiagnosticsPayload, Topics)
{
    EXPECT_EQ(telemetry::boot_topic("climasense", "id"), "climasense/id/boot");
    EXPECT_EQ(telemetry::log_topic("climasense", "id"), "climasense/id/log");
    EXPECT_EQ(telemetry::log_level_topic("climasense", "id"), "climasense/id/set/log_level");
}
