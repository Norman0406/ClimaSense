#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "net/backoff.h"
#include "net/hostname.h"
#include "net/settings.h"

using net::NetSettings;
using net::ReconnectBackoff;
using net::SettingProblem;

namespace {

NetSettings valid_settings()
{
    NetSettings s;
    s.ssid.set("home");
    s.password.set("correct horse");
    s.country.set("CH");
    s.sntp_server.set("ch.pool.ntp.org");
    s.timezone.set("CET-1CEST,M3.5.0,M10.5.0/3");
    return s;
}

}  // namespace

// --- Text --------------------------------------------------------------------------------------

TEST(Text, KeepsValuesUpToItsLimitAndRejectsLongerOnes)
{
    net::Text<4> t;
    EXPECT_TRUE(t.empty());
    EXPECT_TRUE(t.set("abcd"));
    EXPECT_EQ(t.view(), "abcd");
    EXPECT_FALSE(t.set("abcde"));
    EXPECT_EQ(t.view(), "abcd");  // unchanged
    EXPECT_TRUE(t.set("x"));
    EXPECT_EQ(t.view(), "x");     // no leftovers of the longer value
    EXPECT_EQ(std::string(t.c_str()), "x");
}

TEST(Text, LimitsMatchTheWifiDriver)
{
    EXPECT_EQ(decltype(NetSettings::ssid)::kMaxLength, 32u);
    EXPECT_EQ(decltype(NetSettings::password)::kMaxLength, 64u);
}

// --- Validation ----------------------------------------------------------------------------------

TEST(NetSettingsValidation, AcceptsAUsualConfiguration)
{
    EXPECT_FALSE(net::validate(valid_settings()));
    EXPECT_TRUE(net::wifi_configured(valid_settings()));
}

TEST(NetSettingsValidation, EmptySsidIsValidAndMeansNotConfigured)
{
    NetSettings s = valid_settings();
    s.ssid.set("");
    EXPECT_FALSE(net::validate(s));
    EXPECT_FALSE(net::wifi_configured(s));
}

TEST(NetSettingsValidation, OpenNetworkHasNoPassword)
{
    NetSettings s = valid_settings();
    s.password.set("");
    EXPECT_FALSE(net::validate(s));
}

TEST(NetSettingsValidation, PasswordLengthLimits)
{
    NetSettings s = valid_settings();
    s.password.set("1234567");  // 7
    EXPECT_EQ(net::validate(s), SettingProblem::PasswordLength);
    s.password.set("12345678");  // 8
    EXPECT_FALSE(net::validate(s));
    s.password.set(std::string(63, 'a'));
    EXPECT_FALSE(net::validate(s));
}

TEST(NetSettingsValidation, SixtyFourCharactersMustBeAHexKey)
{
    NetSettings s = valid_settings();
    s.password.set(std::string(64, 'f'));
    EXPECT_FALSE(net::validate(s));
    s.password.set(std::string(63, 'f') + "g");
    EXPECT_EQ(net::validate(s), SettingProblem::PasswordLength);
}

TEST(NetSettingsValidation, PasswordMustBePrintableAscii)
{
    NetSettings s = valid_settings();
    s.password.set("abc\tdefgh");
    EXPECT_EQ(net::validate(s), SettingProblem::PasswordCharacters);
}

TEST(NetSettingsValidation, CountryIsTwoCapitalLetters)
{
    NetSettings s = valid_settings();
    for (const char *bad : {"", "C", "ch", "C1"}) {
        s.country.set(bad);
        EXPECT_EQ(net::validate(s), SettingProblem::CountryCode) << "\"" << bad << "\"";
    }
    s.country.set("DE");
    EXPECT_FALSE(net::validate(s));
}

TEST(NetSettingsValidation, TimeServerAndZoneAreNeeded)
{
    NetSettings s = valid_settings();
    s.sntp_server.set("");
    EXPECT_EQ(net::validate(s), SettingProblem::SntpServerEmpty);
    s = valid_settings();
    s.timezone.set("");
    EXPECT_EQ(net::validate(s), SettingProblem::TimezoneEmpty);
}

// --- Reconnect backoff ---------------------------------------------------------------------------

TEST(ReconnectBackoff, DoublesUpToOneMinute)
{
    ReconnectBackoff b;
    std::vector<uint32_t> delays;
    for (int i = 0; i < 9; ++i) {
        delays.push_back(b.next_ms());
    }
    EXPECT_EQ(delays, (std::vector<uint32_t>{1'000, 2'000, 4'000, 8'000, 16'000, 32'000, 60'000, 60'000, 60'000}));
}

TEST(ReconnectBackoff, ResetStartsAgainAtOneSecond)
{
    ReconnectBackoff b;
    b.next_ms();
    b.next_ms();
    b.reset();
    EXPECT_EQ(b.next_ms(), 1'000u);
}

// --- Host name -----------------------------------------------------------------------------------

TEST(Hostname, UsesTheLastThreeMacBytesInLowerCaseHex)
{
    const std::array<uint8_t, 6> mac{0x40, 0x4C, 0xCA, 0xA1, 0xB2, 0x0C};
    const net::Hostname name = net::hostname_from_mac(mac);
    EXPECT_STREQ(name.data(), "climasense-a1b20c");
}

TEST(Hostname, IsAValidHostLabel)
{
    // At most 63 characters; letters, digits and '-' only.
    const std::array<uint8_t, 6> mac{0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    const std::string name = net::hostname_from_mac(mac).data();
    EXPECT_LE(name.size(), 63u);
    for (const char c : name) {
        EXPECT_TRUE((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-') << c;
    }
}
