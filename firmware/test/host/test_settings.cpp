#include <algorithm>
#include <expected>
#include <map>
#include <span>
#include <string>
#include <string_view>

#include <gtest/gtest.h>

#include "settings/device.h"
#include "settings/store.h"
#include "fake_store.h"

using settings::DeviceProblem;
using settings::DeviceSettings;
using settings::KvError;
using settings::SaveError;
namespace key = settings::key;
using test_support::FakeStore;

namespace {

net::NetSettings defaults()
{
    net::NetSettings s;
    s.ssid.set("build-network");
    s.password.set("build-password");
    s.country.set("CH");
    s.sntp_server.set("ch.pool.ntp.org");
    s.timezone.set("CET-1CEST,M3.5.0,M10.5.0/3");
    return s;
}

}  // namespace

// --- Loading -------------------------------------------------------------------------------------

TEST(SettingsStore, NothingStoredGivesTheDefaults)
{
    FakeStore store;
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_EQ(loaded.stored_fields, 0);
    EXPECT_FALSE(loaded.rejected);
    EXPECT_EQ(loaded.value.ssid.view(), "build-network");
    EXPECT_EQ(loaded.value.country.view(), "CH");
}

TEST(SettingsStore, StoredFieldsTakePrecedenceOneByOne)
{
    FakeStore store;
    store.committed[key::kWifiSsid] = "portal-network";
    store.committed[key::kWifiPassword] = "portal-password";
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_EQ(loaded.stored_fields, 2);
    EXPECT_EQ(loaded.value.ssid.view(), "portal-network");
    EXPECT_EQ(loaded.value.password.view(), "portal-password");
    EXPECT_EQ(loaded.value.sntp_server.view(), "ch.pool.ntp.org");  // not stored: default
}

TEST(SettingsStore, AStoredEmptyValueOverridesTheDefault)
{
    // A network cleared in the portal stays cleared, even though the build has one.
    FakeStore store;
    store.committed[key::kWifiSsid] = "";
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_EQ(loaded.stored_fields, 1);
    EXPECT_TRUE(loaded.value.ssid.empty());
    EXPECT_FALSE(net::wifi_configured(loaded.value));
}

TEST(SettingsStore, InvalidStoredValuesFallBackToTheDefaults)
{
    FakeStore store;
    store.committed[key::kWifiSsid] = "portal-network";
    store.committed[key::kWifiCountry] = "ch";  // lower case: invalid
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_TRUE(loaded.rejected);
    EXPECT_EQ(loaded.value.ssid.view(), "build-network");  // all defaults, not a mix
    EXPECT_EQ(loaded.value.country.view(), "CH");
}

TEST(SettingsStore, AValueTooLongForItsFieldIsRejected)
{
    FakeStore store;
    store.committed[key::kWifiSsid] = std::string(33, 'x');  // SSIDs have at most 32 bytes
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_TRUE(loaded.rejected);
    EXPECT_EQ(loaded.value.ssid.view(), "build-network");
}

TEST(SettingsStore, AFailingStoreIsReportedAndDefaultsAreUsed)
{
    FakeStore store;
    store.fail_reads = true;
    const auto loaded = settings::load_net(store, defaults());
    EXPECT_TRUE(loaded.store_failed);
    EXPECT_EQ(loaded.stored_fields, 0);
    EXPECT_EQ(loaded.value.ssid.view(), "build-network");
}

// --- Saving --------------------------------------------------------------------------------------

TEST(SettingsStore, SaveWritesEveryFieldAndCommits)
{
    FakeStore store;
    net::NetSettings s = defaults();
    s.ssid.set("new-network");
    EXPECT_FALSE(settings::save_net(store, s));
    EXPECT_TRUE(store.pending.empty());
    EXPECT_EQ(store.committed.size(), 5u);
    EXPECT_EQ(store.committed[key::kWifiSsid], "new-network");

    const auto loaded = settings::load_net(store, net::NetSettings{});
    EXPECT_EQ(loaded.stored_fields, 5);
    EXPECT_EQ(loaded.value.ssid.view(), "new-network");
    EXPECT_EQ(loaded.value.timezone.view(), "CET-1CEST,M3.5.0,M10.5.0/3");
}

TEST(SettingsStore, InvalidSettingsAreNotWrittenAtAll)
{
    FakeStore store;
    net::NetSettings s = defaults();
    s.password.set("short");
    EXPECT_EQ(settings::save_net(store, s), SaveError::Invalid);
    EXPECT_EQ(store.writes, 0);
    EXPECT_TRUE(store.committed.empty());
}

TEST(SettingsStore, AFailingWriteIsReported)
{
    FakeStore store;
    store.fail_writes = true;
    EXPECT_EQ(settings::save_net(store, defaults()), SaveError::StoreFailed);
    EXPECT_TRUE(store.committed.empty());
}

TEST(SettingsStore, KeysFitNvs)
{
    for (const char *k : {key::kWifiSsid, key::kWifiPassword, key::kWifiCountry, key::kSntpServer,
                          key::kTimezone, key::kDeviceName, key::kStatusLed}) {
        EXPECT_LE(std::string_view(k).size(), 15u) << k;  // NVS: 15 characters plus NUL
    }
}

// --- Device settings -----------------------------------------------------------------------------

TEST(DeviceSettings, NameRoundTripsAndDefaultsToTheId)
{
    FakeStore store;
    DeviceSettings d;
    EXPECT_EQ(settings::display_name(d, "climasense-a1b2c3"), "climasense-a1b2c3");
    d.name.set("Küche");
    EXPECT_FALSE(settings::save_device(store, d));
    const auto loaded = settings::load_device(store, DeviceSettings{});
    EXPECT_EQ(loaded.value.name.view(), "Küche");
    EXPECT_EQ(settings::display_name(loaded.value, "climasense-a1b2c3"), "Küche");
}

TEST(DeviceSettings, StatusLedIsOnByDefaultAndRoundTrips)
{
    FakeStore store;
    EXPECT_TRUE(settings::load_device(store, DeviceSettings{}).value.status_led);
    DeviceSettings d;
    d.status_led = false;
    EXPECT_FALSE(settings::save_device(store, d));
    EXPECT_EQ(store.committed["status_led"], "0");
    EXPECT_FALSE(settings::load_device(store, DeviceSettings{}).value.status_led);
    d.status_led = true;
    EXPECT_FALSE(settings::save_device(store, d));
    EXPECT_TRUE(settings::load_device(store, DeviceSettings{}).value.status_led);
}

TEST(DeviceSettings, StatusLedOtherThanZeroOrOneRejectsTheRecord)
{
    FakeStore store;
    store.committed["device_name"] = "Bedroom";
    store.committed["status_led"] = "off";
    const auto loaded = settings::load_device(store, DeviceSettings{});
    EXPECT_TRUE(loaded.rejected);
    EXPECT_TRUE(loaded.value.status_led);
    EXPECT_TRUE(loaded.value.name.empty());
}

TEST(DeviceSettings, NameMustBeUtf8)
{
    DeviceSettings d;
    for (const char *ok : {"", "Living room", "Küche", "Büro 2", "日本", "🌡 Sensor"}) {
        d.name.set(ok);
        EXPECT_FALSE(settings::validate(d)) << ok;
    }
    const char *bad[] = {
        "\xC3",              // truncated two-byte sequence
        "a\xC3",             // truncated at the end
        "\x80",              // continuation byte alone
        "\xC0\xAF",          // overlong encoding of '/'
        "\xED\xA0\x80",      // surrogate
        "\xF4\x90\x80\x80",  // beyond U+10FFFF
        "\xFF",
    };
    for (const char *b : bad) {
        d.name.set(b);
        EXPECT_EQ(settings::validate(d), DeviceProblem::NameNotUtf8) << "byte 0x" << std::hex
                                                                     << (static_cast<unsigned>(b[0]) & 0xFF);
    }
}

TEST(DeviceSettings, NameMayNotContainControlCharacters)
{
    DeviceSettings d;
    d.name.set("Living\nroom");
    EXPECT_EQ(settings::validate(d), DeviceProblem::NameControlCharacters);
    d.name.set("tab\there");
    EXPECT_EQ(settings::validate(d), DeviceProblem::NameControlCharacters);
}
