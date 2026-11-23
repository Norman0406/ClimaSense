// Find Hub tag frames, the table of tags heard, and the message that reports them.
#include <cstdint>
#include <string>
#include <vector>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "ble/fhn_frame.h"
#include "ble/sightings.h"
#include "telemetry/payload.h"

using ble::FhnFrame;
using ble::Report;
using ble::SightingTable;
using testing::HasSubstr;
using testing::Not;

namespace {

// An advertisement as a tag sends it (Find Hub Network accessory specification, table 16): flags,
// then service data for 0xFEAA with the frame type, the EID and, optionally, the hashed flags.
std::vector<uint8_t> advertisement(uint8_t type, std::size_t eid_len, bool with_flags, uint8_t first = 0x10)
{
    std::vector<uint8_t> adv{0x02, 0x01, 0x06};
    adv.push_back(static_cast<uint8_t>(1 + 2 + 1 + eid_len + (with_flags ? 1 : 0)));
    adv.insert(adv.end(), {0x16, 0xAA, 0xFE, type});
    for (std::size_t i = 0; i < eid_len; ++i) {
        adv.push_back(static_cast<uint8_t>(first + i));
    }
    if (with_flags) {
        adv.push_back(0xA5);
    }
    return adv;
}

FhnFrame frame(uint8_t id, uint8_t type = ble::kFhnFrame)
{
    FhnFrame f;
    f.eid_len = 20;
    f.eid.fill(0);
    f.eid[0] = id;
    f.type = type;
    return f;
}

}  // namespace

// --- Frames --------------------------------------------------------------------------------------

TEST(FhnFrame, TheSpecificationsFrameWithFlags)
{
    const auto adv = advertisement(0x40, 20, true);
    ASSERT_EQ(adv.size(), 29u);  // the specification's octets 0..28
    EXPECT_EQ(adv[3], 0x19);
    const auto f = ble::parse_fhn(adv);
    ASSERT_TRUE(f);
    EXPECT_EQ(f->type, 0x40);
    ASSERT_EQ(f->eid_len, 20);
    EXPECT_EQ(f->eid[0], 0x10);
    EXPECT_EQ(f->eid[19], 0x23);
    ASSERT_TRUE(f->flags);
    EXPECT_EQ(*f->flags, 0xA5);
}

TEST(FhnFrame, WithoutFlagsAndInProtectionMode)
{
    const auto adv = advertisement(0x41, 20, false);
    EXPECT_EQ(adv[3], 0x18);
    const auto f = ble::parse_fhn(adv);
    ASSERT_TRUE(f);
    EXPECT_EQ(f->type, ble::kFhnFrameProtected);
    EXPECT_EQ(f->eid_len, 20);
    EXPECT_FALSE(f->flags);
}

TEST(FhnFrame, ThirtyTwoByteIdentifier)
{
    for (const bool with_flags : {false, true}) {
        const auto f = ble::parse_fhn(advertisement(0x40, 32, with_flags));
        ASSERT_TRUE(f);
        EXPECT_EQ(f->eid_len, 32);
        EXPECT_EQ(f->eid[31], 0x10 + 31);
        EXPECT_EQ(f->flags.has_value(), with_flags);
    }
}

TEST(FhnFrame, FoundAfterOtherStructuresAndWithoutTheFlagsStructure)
{
    std::vector<uint8_t> adv{0x03, 0x03, 0xAA, 0xFE};  // a list of service UUIDs first
    const auto tail = advertisement(0x40, 20, false);
    adv.insert(adv.end(), tail.begin() + 3, tail.end());  // no flags structure
    const auto f = ble::parse_fhn(adv);
    ASSERT_TRUE(f);
    EXPECT_EQ(f->eid[0], 0x10);
}

TEST(FhnFrame, OtherAdvertisementsAreNotFrames)
{
    EXPECT_FALSE(ble::parse_fhn({}));
    // Other Eddystone frame types on the same UUID: UID (0x00), URL (0x10), TLM (0x20).
    for (const uint8_t type : {0x00, 0x10, 0x20, 0x42}) {
        EXPECT_FALSE(ble::parse_fhn(advertisement(type, 20, false))) << int(type);
    }
    // Another service UUID.
    auto other = advertisement(0x40, 20, false);
    other[5] = 0x2C;
    EXPECT_FALSE(ble::parse_fhn(other));
    // Identifiers of another length.
    for (const std::size_t len : {0u, 8u, 19u, 22u, 31u, 34u}) {
        EXPECT_FALSE(ble::parse_fhn(advertisement(0x40, len, false))) << len;
    }
    // An iBeacon (manufacturer data).
    const std::vector<uint8_t> ibeacon{0x02, 0x01, 0x06, 0x1A, 0xFF, 0x4C, 0x00, 0x02, 0x15, 1, 2, 3, 4, 5, 6,
                                       7,    8,    9,    10,   11,   12,   13,   14,   15,   16, 0, 1, 0, 2, 0xC5};
    EXPECT_FALSE(ble::parse_fhn(ibeacon));
}

TEST(FhnFrame, MalformedDataIsRejectedWithoutReadingPastTheEnd)
{
    auto adv = advertisement(0x40, 20, true);
    // Every truncation of a valid advertisement.
    for (std::size_t len = 0; len < adv.size(); ++len) {
        EXPECT_FALSE(ble::parse_fhn(std::span<const uint8_t>(adv.data(), len))) << len;
    }
    // A structure length that runs past the end.
    adv[3] = 0x30;
    EXPECT_FALSE(ble::parse_fhn(adv));
    // Zero padding after the data ends the search.
    auto padded = advertisement(0x40, 20, false);
    padded.insert(padded.end(), {0x00, 0x00, 0x00});
    EXPECT_TRUE(ble::parse_fhn(padded));
    // A length byte as the very last byte.
    const std::vector<uint8_t> lone{0x02, 0x01, 0x06, 0x05};
    EXPECT_FALSE(ble::parse_fhn(lone));
}

// --- Table ---------------------------------------------------------------------------------------

TEST(Sightings, ANewTagIsNewOnce)
{
    SightingTable table;
    EXPECT_TRUE(table.add(frame(1), -70, 100));
    EXPECT_FALSE(table.add(frame(1), -60, 101));
    EXPECT_TRUE(table.add(frame(2), -80, 102));
    // The same bytes as a 32-byte identifier are another tag.
    FhnFrame longer = frame(1);
    longer.eid_len = 32;
    EXPECT_TRUE(table.add(longer, -80, 103));
}

TEST(Sightings, AReportListsWhatWasHeardInTheWindow)
{
    SightingTable table;
    Report report;
    table.take_report(1000, report);  // starts a window
    FhnFrame f = frame(1);
    f.flags = 0x3A;
    table.add(f, -75, 1010);
    table.add(frame(1, ble::kFhnFrameProtected), -62, 1020);  // stronger, other type, no flags
    table.add(frame(1, ble::kFhnFrameProtected), -70, 1030);
    table.add(frame(2), ble::kRssiUnknown, 1040);
    table.take_report(1060, report);
    EXPECT_EQ(report.window_s, 60u);
    EXPECT_EQ(report.dropped, 0u);
    ASSERT_EQ(report.count, 2u);
    EXPECT_EQ(report.heard[0].eid[0], 1);
    EXPECT_EQ(report.heard[0].count, 3);
    EXPECT_EQ(report.heard[0].rssi, -62);                       // the strongest
    EXPECT_EQ(report.heard[0].type, ble::kFhnFrameProtected);   // the latest
    EXPECT_FALSE(report.heard[0].flags);                        // the latest
    EXPECT_EQ(report.heard[0].last_s, 1030u);
    EXPECT_EQ(report.heard[1].eid[0], 2);
    EXPECT_EQ(report.heard[1].rssi, ble::kRssiUnknown);
}

TEST(Sightings, TheNextWindowStartsEmptyAndWithFreshSignalStrength)
{
    SightingTable table;
    Report report;
    table.add(frame(1), -50, 10);
    table.take_report(60, report);
    ASSERT_EQ(report.count, 1u);
    table.take_report(120, report);
    EXPECT_EQ(report.count, 0u);  // not heard in this window
    EXPECT_EQ(report.window_s, 60u);
    EXPECT_FALSE(table.add(frame(1), -80, 125));  // still known
    table.take_report(180, report);
    ASSERT_EQ(report.count, 1u);
    EXPECT_EQ(report.heard[0].rssi, -80);  // not the -50 of an earlier window
    EXPECT_EQ(report.heard[0].count, 1);
}

TEST(Sightings, AnUnknownSignalStrengthDoesNotHideAKnownOne)
{
    SightingTable table;
    Report report;
    table.add(frame(1), ble::kRssiUnknown, 1);
    table.add(frame(1), -77, 2);
    table.add(frame(1), ble::kRssiUnknown, 3);
    table.take_report(10, report);
    EXPECT_EQ(report.heard[0].rssi, -77);
}

TEST(Sightings, ATagNotHeardForTwoMinutesIsNewAgain)
{
    SightingTable table;
    Report report;
    EXPECT_TRUE(table.add(frame(1), -70, 0));
    EXPECT_FALSE(table.add(frame(1), -70, ble::kForgetAfterS - 1));
    // Forgotten by a report in between ...
    table.take_report(2 * ble::kForgetAfterS, report);
    EXPECT_TRUE(table.add(frame(1), -70, 2 * ble::kForgetAfterS + 1));
    // ... and also without one.
    EXPECT_TRUE(table.add(frame(1), -70, 3 * ble::kForgetAfterS + 1));
    EXPECT_FALSE(table.add(frame(1), -70, 3 * ble::kForgetAfterS + 2));
}

TEST(Sightings, AFullTableDropsFurtherTagsAndCountsThem)
{
    SightingTable table;
    Report report;
    for (std::size_t i = 0; i < ble::kMaxSightings; ++i) {
        EXPECT_TRUE(table.add(frame(static_cast<uint8_t>(i + 1)), -70, 5));
    }
    EXPECT_FALSE(table.add(frame(200), -70, 6));
    EXPECT_FALSE(table.add(frame(200), -70, 7));
    EXPECT_FALSE(table.add(frame(1), -70, 8));  // known tags are still recorded
    table.take_report(60, report);
    EXPECT_EQ(report.count, ble::kMaxSightings);
    EXPECT_EQ(report.dropped, 2u);
    table.take_report(70, report);
    EXPECT_EQ(report.dropped, 0u);
}

TEST(Sightings, AFullTableMakesRoomByForgettingTheTagHeardLongestAgo)
{
    SightingTable table;
    Report report;
    for (std::size_t i = 0; i < ble::kMaxSightings; ++i) {
        table.add(frame(static_cast<uint8_t>(i + 1)), -70, static_cast<uint32_t>(10 + i));
    }
    table.take_report(60, report);  // nothing heard in the new window yet
    EXPECT_TRUE(table.add(frame(200), -70, 61));  // takes the place of tag 1, the stalest
    EXPECT_TRUE(table.add(frame(1), -70, 62));    // tag 1 was forgotten: takes the place of tag 2
    EXPECT_FALSE(table.add(frame(3), -70, 63));   // tag 3 is still known
    table.take_report(70, report);
    EXPECT_EQ(report.count, 3u);
    EXPECT_EQ(report.dropped, 0u);
}

// --- Message -------------------------------------------------------------------------------------

TEST(BleMessage, Topic) { EXPECT_EQ(telemetry::ble_topic("climasense", "climasense-a1b2c3"), "climasense/climasense-a1b2c3/ble"); }

TEST(BleMessage, ListsTheTagsHeard)
{
    SightingTable table;
    Report report;
    table.take_report(1000, report);
    FhnFrame a;
    a.eid_len = 20;
    for (std::size_t i = 0; i < 20; ++i) {
        a.eid[i] = static_cast<uint8_t>(0xF0 + i);  // f0 f1 ... ff 00 01 02 03
    }
    a.type = 0x40;
    a.flags = 0x0B;
    table.add(a, -71, 1050);
    table.add(a, -64, 1057);
    table.add(frame(0xAB, 0x41), ble::kRssiUnknown, 1058);
    table.take_report(1060, report);

    const std::string json =
        telemetry::ble_json(report, {"climasense-a1b2c3", "2026-11-23T18:04:05+01:00", 1060});
    EXPECT_EQ(json, "{\"id\":\"climasense-a1b2c3\",\"time\":\"2026-11-23T18:04:05+01:00\",\"window_s\":60,"
                    "\"fhn\":["
                    "{\"eid\":\"f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff00010203\",\"type\":64,\"flags\":\"0b\","
                    "\"rssi\":-64,\"count\":2,\"age_s\":3},"
                    "{\"eid\":\"ab00000000000000000000000000000000000000\",\"type\":65,\"count\":1,\"age_s\":2}"
                    "]}");
}

TEST(BleMessage, AnEmptyListAndNoTimeBeforeTheClockIsSet)
{
    Report report;
    report.window_s = 60;
    EXPECT_EQ(telemetry::ble_json(report, {"climasense-a1b2c3", "", 60}),
              "{\"id\":\"climasense-a1b2c3\",\"window_s\":60,\"fhn\":[]}");
}

TEST(BleMessage, SaysWhenFramesWereDropped)
{
    Report report;
    report.window_s = 60;
    report.dropped = 7;
    EXPECT_THAT(telemetry::ble_json(report, {"x", "", 60}), HasSubstr("\"window_s\":60,\"dropped\":7,\"fhn\":[]"));
    report.dropped = 0;
    EXPECT_THAT(telemetry::ble_json(report, {"x", "", 60}), Not(HasSubstr("dropped")));
}

TEST(BleMessage, AFullReportFitsTheMqttBuffer)
{
    SightingTable table;
    Report report;
    for (std::size_t i = 0; i < ble::kMaxSightings; ++i) {
        FhnFrame f;
        f.eid_len = 32;
        f.eid.fill(static_cast<uint8_t>(i + 1));
        f.type = 0x41;
        f.flags = 0xFF;
        for (int n = 0; n < 70000; ++n) {
            table.add(f, -100, 4'000'000'000u);  // the count saturates
        }
    }
    table.take_report(4'000'000'100u, report);
    ASSERT_EQ(report.count, ble::kMaxSightings);
    EXPECT_EQ(report.heard[0].count, 65535);
    report.dropped = 4'000'000'000u;
    const std::string json = telemetry::ble_json(
        report, {"climasense-a1b2c3", "2026-11-23T18:04:05+01:00", 4'000'000'100u});
    // The client's buffer is 4096 bytes and also holds the topic and the MQTT header.
    EXPECT_LT(json.size(), 3900u);
}
