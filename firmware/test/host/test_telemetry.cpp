#include <algorithm>
#include <string>
#include <string_view>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "fake_store.h"
#include "portal/form.h"
#include "portal/page.h"
#include "sensors/snapshot.h"
#include "settings/store.h"
#include "telemetry/mqtt_settings.h"
#include "telemetry/payload.h"

using ::testing::HasSubstr;
using ::testing::Not;
using telemetry::MqttProblem;
using telemetry::MqttSettings;
using test_support::FakeStore;
namespace key = settings::key;

namespace {

MqttSettings broker()
{
    MqttSettings m;
    m.host.set("mosquitto.local");
    m.username.set("sensor");
    m.password.set("mqtt-secret");
    return m;
}

// A valid network record: the form checks every record, so the MQTT tests need one.
net::NetSettings net_ok()
{
    net::NetSettings n;
    n.country.set("CH");
    n.sntp_server.set("ch.pool.ntp.org");
    n.timezone.set("CET-1CEST,M3.5.0,M10.5.0/3");
    return n;
}

bool has_error(const portal::FormResult &r, std::string_view field)
{
    return std::any_of(r.errors.begin(), r.errors.end(), [&](const portal::FieldError &e) { return e.field == field; });
}

}  // namespace

// --- MQTT settings rules -------------------------------------------------------------------------

TEST(MqttSettings, DefaultsAreValidAndOff)
{
    const MqttSettings m;
    EXPECT_FALSE(telemetry::validate(m));
    EXPECT_FALSE(telemetry::mqtt_configured(m));
    EXPECT_EQ(m.port, 1883);
    EXPECT_EQ(m.base_topic.view(), "climasense");
    EXPECT_EQ(m.ha_prefix.view(), "homeassistant");
    EXPECT_FALSE(m.ha_discovery);
}

TEST(MqttSettings, HostIsAHostNameOrAddress)
{
    MqttSettings m = broker();
    EXPECT_FALSE(telemetry::validate(m));
    m.host.set("192.168.1.10");
    EXPECT_FALSE(telemetry::validate(m));
    m.host.set("mqtt://broker");
    EXPECT_EQ(telemetry::validate(m), MqttProblem::HostCharacters);
    m.host.set("my broker");
    EXPECT_EQ(telemetry::validate(m), MqttProblem::HostCharacters);
}

TEST(MqttSettings, PortZeroAndPasswordWithoutUserAreInvalid)
{
    MqttSettings m = broker();
    m.port = 0;
    EXPECT_EQ(telemetry::validate(m), MqttProblem::Port);
    m = broker();
    m.username.set("");
    EXPECT_EQ(telemetry::validate(m), MqttProblem::PasswordWithoutUser);
}

TEST(MqttSettings, TopicRules)
{
    for (const char *ok : {"climasense", "home/sensors", "a-b_c/d1"}) {
        EXPECT_TRUE(telemetry::valid_topic(ok)) << ok;
    }
    for (const char *bad : {"", "/climasense", "climasense/", "a//b", "a/+/b", "a/#", "with space", "k\xC3\xBC"}) {
        EXPECT_FALSE(telemetry::valid_topic(bad)) << bad;
    }
}

// --- Store ---------------------------------------------------------------------------------------

TEST(MqttStore, PortParsingIsStrict)
{
    EXPECT_EQ(settings::parse_port("1883"), 1883);
    EXPECT_EQ(settings::parse_port("1"), 1);
    EXPECT_EQ(settings::parse_port("65535"), 65535);
    for (const char *bad : {"", "0", "01883", "65536", "-1", "+1", " 1883", "18a3", "123456"}) {
        EXPECT_FALSE(settings::parse_port(bad)) << bad;
    }
}

TEST(MqttStore, RoundTrip)
{
    FakeStore store;
    MqttSettings m = broker();
    m.port = 8883;
    m.ha_discovery = true;
    m.base_topic.set("home/climate");
    EXPECT_FALSE(settings::save_mqtt(store, m));
    EXPECT_EQ(store.committed[key::kMqttPort], "8883");
    EXPECT_EQ(store.committed[key::kHaDiscovery], "1");

    const auto loaded = settings::load_mqtt(store, MqttSettings{});
    EXPECT_FALSE(loaded.rejected);
    EXPECT_EQ(loaded.stored_fields, 7);
    EXPECT_EQ(loaded.value.host.view(), "mosquitto.local");
    EXPECT_EQ(loaded.value.port, 8883);
    EXPECT_TRUE(loaded.value.ha_discovery);
    EXPECT_EQ(loaded.value.base_topic.view(), "home/climate");
}

TEST(MqttStore, BadStoredPortOrSwitchFallsBackToDefaults)
{
    FakeStore store;
    store.committed[key::kMqttHost] = "broker";
    store.committed[key::kMqttPort] = "99999";
    auto loaded = settings::load_mqtt(store, MqttSettings{});
    EXPECT_TRUE(loaded.rejected);
    EXPECT_TRUE(loaded.value.host.empty());

    store.committed[key::kMqttPort] = "1883";
    store.committed[key::kHaDiscovery] = "yes";
    loaded = settings::load_mqtt(store, MqttSettings{});
    EXPECT_TRUE(loaded.rejected);
}

TEST(MqttStore, InvalidSettingsAreNotWritten)
{
    FakeStore store;
    MqttSettings m = broker();
    m.base_topic.set("a/#");
    EXPECT_EQ(settings::save_mqtt(store, m), settings::SaveError::Invalid);
    EXPECT_EQ(store.writes, 0);
}

TEST(MqttStore, KeysFitNvs)
{
    for (const char *k : {key::kMqttHost, key::kMqttPort, key::kMqttUser, key::kMqttPassword, key::kMqttBaseTopic,
                          key::kHaDiscovery, key::kHaPrefix}) {
        EXPECT_LE(std::string_view(k).size(), 15u) << k;
    }
}

// --- Snapshot ------------------------------------------------------------------------------------

TEST(Snapshot, MeansRoundHalfAwayFromZero)
{
    sensors::Mean m;
    EXPECT_FALSE(m.value());
    m.add(1);
    m.add(2);
    EXPECT_EQ(m.value(), 2);  // 1.5 -> 2
    sensors::Mean n;
    n.add(-1);
    n.add(-2);
    EXPECT_EQ(n.value(), -2);  // -1.5 -> -2
}

TEST(Snapshot, AveragesTheWindowAndStartsANewOne)
{
    sensors::SnapshotBuilder b;
    b.add_temperature_humidity(22'000, 40'000);
    b.add_temperature_humidity(23'000, 42'000);
    b.add_pressure(96'300'000);
    const auto s = b.take(60);
    EXPECT_EQ(s.temperature_mc, 22'500);
    EXPECT_EQ(s.humidity_mpercent, 41'000);
    EXPECT_EQ(s.pressure_milli_pa, 96'300'000);
    EXPECT_EQ(s.sht45_samples, 2u);

    const auto next = b.take(120);  // nothing new
    EXPECT_FALSE(next.temperature_mc);
    EXPECT_FALSE(next.pressure_milli_pa);
}

TEST(Snapshot, Co2CarriesOverUntilItIsTooOld)
{
    sensors::SnapshotBuilder b;
    b.set_co2(812, 100);
    const auto first = b.take(160);
    EXPECT_EQ(first.co2_ppm, 812);
    EXPECT_EQ(first.co2_age_s, 60u);
    EXPECT_EQ(b.take(100 + sensors::SnapshotBuilder::kCo2MaxAgeS).co2_ppm, 812);
    const auto too_old = b.take(101 + sensors::SnapshotBuilder::kCo2MaxAgeS);
    EXPECT_FALSE(too_old.co2_ppm);
    EXPECT_FALSE(too_old.co2_age_s);  // no age without a value
}

TEST(Snapshot, GasIndexIsLeftOutWhileStartingAndAfterAQuietWindow)
{
    sensors::SnapshotBuilder b;
    b.set_gas_index(0, 0);  // blackout
    auto s = b.take(60);
    EXPECT_FALSE(s.voc_index);
    EXPECT_FALSE(s.nox_index);
    b.set_gas_index(104, 1);
    s = b.take(120);
    EXPECT_EQ(s.voc_index, 104);
    EXPECT_EQ(s.nox_index, 1);
    EXPECT_FALSE(b.take(180).voc_index);  // no sample in this window
}

// --- Payload -------------------------------------------------------------------------------------

TEST(Payload, FixedPointFormatting)
{
    EXPECT_EQ(telemetry::fixed(22'415, 1000, 2), "22.42");
    EXPECT_EQ(telemetry::fixed(22'414, 1000, 2), "22.41");
    EXPECT_EQ(telemetry::fixed(-50, 1000, 2), "-0.05");
    EXPECT_EQ(telemetry::fixed(-4, 1000, 2), "0.00");
    EXPECT_EQ(telemetry::fixed(96'312'000, 100'000, 2), "963.12");
    EXPECT_EQ(telemetry::fixed(5, 1, 0), "5");
}

TEST(Payload, JsonEscaping)
{
    EXPECT_EQ(telemetry::json_escape("a\"b\\c"), "a\\\"b\\\\c");
    EXPECT_EQ(telemetry::json_escape("line\nnext\x01"), "line\\nnext\\u0001");
    EXPECT_EQ(telemetry::json_escape("Küche"), "Küche");
}

TEST(Payload, Rfc3339Offset)
{
    EXPECT_EQ(telemetry::rfc3339_offset("2026-11-20T14:05:00+0100"), "2026-11-20T14:05:00+01:00");
    EXPECT_EQ(telemetry::rfc3339_offset("2026-07-01T08:00:00-0430"), "2026-07-01T08:00:00-04:30");
}

TEST(Payload, StateJsonHasAllValues)
{
    sensors::SensorSnapshot s;
    s.temperature_mc = 22'412;
    s.humidity_mpercent = 45'200;
    s.pressure_milli_pa = 96'312'000;
    s.co2_ppm = 812;
    s.co2_age_s = 140;
    s.voc_index = 104;
    s.nox_index = 1;
    const std::string json = telemetry::state_json(
        s, {"climasense-a1b2c3", "Living room", "2026-11-20T14:05:00+01:00", -58, 3600});
    EXPECT_EQ(json,
              "{\"id\":\"climasense-a1b2c3\",\"name\":\"Living room\",\"time\":\"2026-11-20T14:05:00+01:00\","
              "\"temperature_c\":22.41,\"humidity_pct\":45.20,\"pressure_hpa\":963.12,\"co2_ppm\":812,"
              "\"co2_age_s\":140,"
              "\"voc_index\":104,\"nox_index\":1,\"rssi_dbm\":-58,\"uptime_s\":3600}");
}

TEST(Payload, MissingValuesAreLeftOutNotZero)
{
    sensors::SensorSnapshot s;
    s.temperature_mc = 21'000;
    const std::string json = telemetry::state_json(s, {"id", "Na\"me", "", std::nullopt, 5});
    EXPECT_THAT(json, Not(HasSubstr("co2_ppm")));
    EXPECT_THAT(json, Not(HasSubstr("co2_age_s")));
    EXPECT_THAT(json, Not(HasSubstr("\"time\"")));  // the key; "uptime_s" contains the word
    EXPECT_THAT(json, Not(HasSubstr("rssi_dbm")));
    EXPECT_THAT(json, HasSubstr("\"name\":\"Na\\\"me\""));
    EXPECT_THAT(json, HasSubstr("\"temperature_c\":21.00"));
}

TEST(Payload, Topics)
{
    EXPECT_EQ(telemetry::state_topic("climasense", "climasense-a1b2c3"), "climasense/climasense-a1b2c3/state");
    EXPECT_EQ(telemetry::status_topic("home/climate", "x"), "home/climate/x/status");
    EXPECT_EQ(telemetry::ha_status_topic("homeassistant"), "homeassistant/status");
}

// --- Home Assistant discovery --------------------------------------------------------------------

TEST(Discovery, OneRetainedConfigPerValue)
{
    const auto messages = telemetry::discovery_messages(
        {"homeassistant", "climasense", "climasense-a1b2c3", "Living \"room\"", "v1.0"});
    ASSERT_EQ(messages.size(), 9u);
    EXPECT_EQ(messages[0].topic, "homeassistant/sensor/climasense-a1b2c3/temperature_c/config");

    const std::string &t = messages[0].payload;
    EXPECT_THAT(t, HasSubstr("\"unique_id\":\"climasense-a1b2c3_temperature_c\""));
    EXPECT_THAT(t, HasSubstr("\"state_topic\":\"climasense/climasense-a1b2c3/state\""));
    EXPECT_THAT(t, HasSubstr("\"value_template\":\"{{ value_json.temperature_c }}\""));
    EXPECT_THAT(t, HasSubstr("\"unit_of_measurement\":\"°C\""));
    EXPECT_THAT(t, HasSubstr("\"device_class\":\"temperature\""));
    EXPECT_THAT(t, HasSubstr("\"availability_topic\":\"climasense/climasense-a1b2c3/status\""));
    EXPECT_THAT(t, HasSubstr("\"name\":\"Living \\\"room\\\"\""));  // device name escaped
    EXPECT_THAT(t, Not(HasSubstr("entity_category")));
}

TEST(Discovery, IndicesHaveNoClassAndDiagnosticsAreMarked)
{
    const auto messages = telemetry::discovery_messages({"homeassistant", "climasense", "id", "n", "v"});
    const auto find = [&](std::string_view field) {
        return *std::find_if(messages.begin(), messages.end(),
                             [&](const telemetry::Message &m) { return m.topic.find(field) != std::string::npos; });
    };
    EXPECT_THAT(find("voc_index").payload, Not(HasSubstr("device_class")));
    EXPECT_THAT(find("rssi_dbm").payload, HasSubstr("\"entity_category\":\"diagnostic\""));
    EXPECT_THAT(find("uptime_s").payload, HasSubstr("\"device_class\":\"duration\""));
    EXPECT_THAT(find("co2_age_s").payload, HasSubstr("\"entity_category\":\"diagnostic\""));
}

// --- Portal: MQTT fields -------------------------------------------------------------------------

TEST(PortalMqtt, BrokerFieldsAreApplied)
{
    const auto r = portal::apply_form("mqtt_form=1&mqtt_host=10.0.0.5&mqtt_port=1884&mqtt_user=s&mqtt_pass=pw"
                                      "&mqtt_topic=home%2Fclimate&ha=1&ha_prefix=hass",
                                      net_ok(), {}, MqttSettings{});
    ASSERT_TRUE(r.ok()) << r.errors[0].message;
    EXPECT_EQ(r.mqtt.host.view(), "10.0.0.5");
    EXPECT_EQ(r.mqtt.port, 1884);
    EXPECT_EQ(r.mqtt.password.view(), "pw");
    EXPECT_EQ(r.mqtt.base_topic.view(), "home/climate");
    EXPECT_TRUE(r.mqtt.ha_discovery);
    EXPECT_EQ(r.mqtt.ha_prefix.view(), "hass");
}

TEST(PortalMqtt, EmptyPasswordKeepsItNoPasswordClearsIt)
{
    auto r = portal::apply_form("mqtt_form=1&mqtt_host=mosquitto.local&mqtt_user=sensor&mqtt_pass=",
                                net_ok(), {}, broker());
    ASSERT_TRUE(r.ok());
    EXPECT_EQ(r.mqtt.password.view(), "mqtt-secret");

    r = portal::apply_form("mqtt_form=1&mqtt_user=sensor&mqtt_pass=&mqtt_nopass=1", net_ok(), {}, broker());
    ASSERT_TRUE(r.ok());
    EXPECT_TRUE(r.mqtt.password.empty());

    r = portal::apply_form("mqtt_form=1&mqtt_pass=x&mqtt_nopass=1", net_ok(), {}, broker());
    EXPECT_TRUE(has_error(r, portal::field::kMqttPassword));
}

TEST(PortalMqtt, ClearingTheUserClearsThePassword)
{
    const auto r = portal::apply_form("mqtt_form=1&mqtt_user=&mqtt_pass=", net_ok(), {}, broker());
    ASSERT_TRUE(r.ok());
    EXPECT_TRUE(r.mqtt.username.empty());
    EXPECT_TRUE(r.mqtt.password.empty());
}

TEST(PortalMqtt, UntickedCheckboxTurnsDiscoveryOffOnlyWithTheMarker)
{
    MqttSettings on = broker();
    on.ha_discovery = true;
    EXPECT_FALSE(portal::apply_form("mqtt_form=1", net_ok(), {}, on).mqtt.ha_discovery);
    EXPECT_TRUE(portal::apply_form("", net_ok(), {}, on).mqtt.ha_discovery);  // no MQTT section sent
}

TEST(PortalMqtt, BadPortHostAndTopicAreReported)
{
    EXPECT_TRUE(has_error(portal::apply_form("mqtt_port=0", net_ok(), {}, broker()), portal::field::kMqttPort));
    EXPECT_TRUE(has_error(portal::apply_form("mqtt_port=abc", net_ok(), {}, broker()), portal::field::kMqttPort));
    EXPECT_TRUE(has_error(portal::apply_form("mqtt_host=a%20b", net_ok(), {}, broker()), portal::field::kMqttHost));
    EXPECT_TRUE(has_error(portal::apply_form("mqtt_topic=a%2F%23", net_ok(), {}, broker()), portal::field::kMqttTopic));
}

TEST(PortalMqtt, PageShowsBrokerButNeverItsPassword)
{
    const MqttSettings m = broker();
    const net::NetSettings net;
    const settings::DeviceSettings device;
    portal::PageModel model;
    model.device_id = "climasense-a1b2c3";
    model.net = &net;
    model.device = &device;
    model.mqtt = &m;
    model.mqtt_password_stored = true;
    const std::string page = portal::render_settings_page(model);
    EXPECT_THAT(page, HasSubstr("value=\"mosquitto.local\""));
    EXPECT_THAT(page, HasSubstr("value=\"1883\""));
    EXPECT_THAT(page, HasSubstr("name=\"mqtt_form\""));
    EXPECT_THAT(page, Not(HasSubstr("mqtt-secret")));
}
