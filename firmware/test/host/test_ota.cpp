#include <array>
#include <cstdint>
#include <cstring>
#include <string>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "ota/logic.h"

using ota::TrialGuard;
using ota::VersionCheck;
using ::testing::HasSubstr;

namespace {

// The start of an ESP image: magic byte, app description magic at 32, version at 48 (as in the
// real climasense.bin, checked when this was written).
std::array<uint8_t, ota::kImageHeadBytes> image_head(const char *version)
{
    std::array<uint8_t, ota::kImageHeadBytes> head{};
    head[0] = 0xE9;
    const uint32_t magic = 0xABCD5432u;
    std::memcpy(head.data() + 32, &magic, 4);  // little-endian on the PC as on the chip
    std::memcpy(head.data() + ota::kImageVersionOffset, version, std::min<std::size_t>(std::strlen(version), 32));
    return head;
}

}  // namespace

TEST(OtaVersion, ParsesThreeNumbers)
{
    EXPECT_EQ(ota::parse_version("0.1.0"), (ota::Version{0, 1, 0}));
    EXPECT_EQ(ota::parse_version("v1.2.3"), (ota::Version{1, 2, 3}));
    EXPECT_EQ(ota::parse_version("10.20.300"), (ota::Version{10, 20, 300}));
    EXPECT_EQ(ota::parse_version("0.2.0+1a2b3c4"), (ota::Version{0, 2, 0}));  // a release
    for (const char *bad : {"", "1", "1.2", "1.2.3.4", "1..3", "a.b.c", "1.2.3-dirty", " 1.2.3", "53ccfc3",
                            "main-1a2b3c4", "main-1a2b3c4-dirty", "1.2.3+", "unknown"}) {
        EXPECT_FALSE(ota::parse_version(bad)) << bad;
    }
}

TEST(OtaVersion, ComparesNumericallyNotAlphabetically)
{
    EXPECT_EQ(ota::check_version("0.9.0", "0.10.0"), VersionCheck::Newer);
    EXPECT_EQ(ota::check_version("1.2.3", "1.2.3"), VersionCheck::Same);
    EXPECT_EQ(ota::check_version("1.2.3", "1.2.2"), VersionCheck::Older);
    EXPECT_EQ(ota::check_version("1.2.3", "dev-build"), VersionCheck::Unknown);
    EXPECT_EQ(ota::check_version("53ccfc3", "0.1.0"), VersionCheck::Newer);  // running one not comparable
}

TEST(OtaVersion, ReleasesCompareByNumberAndBranchBuildsAreNotComparable)
{
    EXPECT_EQ(ota::check_version("0.2.0+1a2b3c4", "0.2.0+9f8e7d6"), VersionCheck::Same);   // hash ignored
    EXPECT_EQ(ota::check_version("0.2.0+1a2b3c4", "0.3.0+0000000"), VersionCheck::Newer);
    EXPECT_EQ(ota::check_version("0.3.0+0000000", "0.2.0+1a2b3c4"), VersionCheck::Older);
    EXPECT_EQ(ota::check_version("0.2.0+1a2b3c4", "main-1a2b3c4"), VersionCheck::Unknown);  // needs force
    EXPECT_EQ(ota::check_version("main-1a2b3c4-dirty", "0.2.0+1a2b3c4"), VersionCheck::Newer);
}

TEST(OtaVersion, OnlyOlderOrUnknownNeedForce)
{
    EXPECT_TRUE(ota::allowed(VersionCheck::Newer, false));
    EXPECT_TRUE(ota::allowed(VersionCheck::Same, false));
    EXPECT_FALSE(ota::allowed(VersionCheck::Older, false));
    EXPECT_FALSE(ota::allowed(VersionCheck::Unknown, false));
    EXPECT_TRUE(ota::allowed(VersionCheck::Older, true));
}

TEST(OtaCommand, UrlAndOptionalForce)
{
    auto c = ota::parse_update_command("http://192.168.1.5:8000/climasense.bin");
    ASSERT_TRUE(c);
    EXPECT_EQ(c->url, "http://192.168.1.5:8000/climasense.bin");
    EXPECT_FALSE(c->force);

    c = ota::parse_update_command("  https://nas.local/fw/climasense.bin   force\n");
    ASSERT_TRUE(c);
    EXPECT_EQ(c->url, "https://nas.local/fw/climasense.bin");
    EXPECT_TRUE(c->force);
}

TEST(OtaCommand, RejectsAnythingElse)
{
    for (const char *bad : {"", "climasense.bin", "ftp://host/fw.bin", "http://", "https://", "http://host/a.bin now",
                            "http://host/a\tb.bin", "http://host/a.bin force extra"}) {
        EXPECT_FALSE(ota::parse_update_command(bad)) << bad;
    }
}

TEST(OtaImage, ReadsTheVersion)
{
    EXPECT_EQ(ota::image_version(image_head("0.2.0")), "0.2.0");
    // A version filling all 32 bytes, without NUL.
    EXPECT_EQ(ota::image_version(image_head("12345678901234567890123456789012")), "12345678901234567890123456789012");
}

TEST(OtaImage, RejectsWhatIsNotAnEspImage)
{
    auto head = image_head("0.2.0");
    head[0] = 0x7F;  // e.g. an ELF file
    EXPECT_FALSE(ota::image_version(head));
    head = image_head("0.2.0");
    head[33] = 0;  // app description magic broken
    EXPECT_FALSE(ota::image_version(head));
    const auto full = image_head("0.2.0");
    EXPECT_FALSE(ota::image_version(std::span<const uint8_t>(full.data(), full.size() - 1)));  // too short
}

TEST(OtaTrial, AcceptsOnceHealthyAfterThreeMinutes)
{
    const TrialGuard guard;
    EXPECT_EQ(guard.check(10, true), TrialGuard::Verdict::Wait);
    EXPECT_EQ(guard.check(TrialGuard::kMinTrialS - 1, true), TrialGuard::Verdict::Wait);
    EXPECT_EQ(guard.check(TrialGuard::kMinTrialS, true), TrialGuard::Verdict::Accept);
    EXPECT_EQ(guard.check(TrialGuard::kMinTrialS, false), TrialGuard::Verdict::Wait);
}

TEST(OtaTrial, RejectsWhenNotHealthyWithinTenMinutes)
{
    const TrialGuard guard;
    EXPECT_EQ(guard.check(TrialGuard::kMaxTrialS - 1, false), TrialGuard::Verdict::Wait);
    EXPECT_EQ(guard.check(TrialGuard::kMaxTrialS, false), TrialGuard::Verdict::Reject);
    EXPECT_EQ(guard.check(TrialGuard::kMaxTrialS, true), TrialGuard::Verdict::Accept);  // healthy wins
}

TEST(OtaTrial, HealthDependsOnWhatIsConfigured)
{
    EXPECT_TRUE(ota::trial_healthy(true, true, true, true));
    EXPECT_FALSE(ota::trial_healthy(true, false, true, true));   // broker set but not connected
    EXPECT_TRUE(ota::trial_healthy(false, false, true, true));   // no broker: Wi-Fi counts
    EXPECT_FALSE(ota::trial_healthy(false, false, true, false));
    EXPECT_TRUE(ota::trial_healthy(false, false, false, false)); // nothing configured: nothing to check
}

TEST(OtaStatus, Messages)
{
    EXPECT_EQ(ota::status_json("downloading", 40), "{\"state\":\"downloading\",\"progress\":40}");
    EXPECT_EQ(ota::status_json("refused", std::nullopt, "version \"0.1.0\" is older"),
              "{\"state\":\"refused\",\"detail\":\"version \\\"0.1.0\\\" is older\"}");
    EXPECT_THAT(ota::status_json("restarting", 100, "0.2.0"), HasSubstr("\"progress\":100"));
}
