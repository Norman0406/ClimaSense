#include "net/wifi.h"

#include <algorithm>
#include <atomic>
#include <cinttypes>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <ctime>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "net/backoff.h"
#include "net/hostname.h"

namespace net {

namespace {

constexpr const char *kTag = "wifi";

NetSettings g_settings;  // copy kept for the life of the program (SNTP keeps the server pointer)
Hostname g_hostname{};
esp_netif_t *g_netif = nullptr;
esp_timer_handle_t g_reconnect_timer = nullptr;
ReconnectBackoff g_backoff;
std::atomic<bool> g_connected{false};
std::atomic<bool> g_time_synced{false};
bool g_sntp_started = false;
bool g_wifi_started = false;
// Setup mode (portal): an access point next to the station, and no reconnect attempts meanwhile,
// so the station does not leave the access point's channel to search.
esp_netif_t *g_ap_netif = nullptr;
std::atomic<bool> g_reconnect_paused{false};
std::atomic<bool> g_reconnect_pending{false};
char g_portal_uri[24] = {};  // DHCP option 114; lwIP keeps the pointer

void on_time_sync(struct timeval *tv)
{
    g_time_synced = true;
    time_t now = tv->tv_sec;
    struct tm local {};
    localtime_r(&now, &local);
    char text[32];
    strftime(text, sizeof(text), "%Y-%m-%d %H:%M:%S %Z", &local);
    ESP_LOGI(kTag, "time synchronised: %s", text);
}

void start_sntp()
{
    if (g_sntp_started) {
        return;  // keeps running and resyncing on its own
    }
    g_sntp_started = true;
    setenv("TZ", g_settings.timezone.c_str(), 1);
    tzset();
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(g_settings.sntp_server.c_str());
    config.sync_cb = on_time_sync;
    if (const esp_err_t err = esp_netif_sntp_init(&config); err != ESP_OK) {
        ESP_LOGW(kTag, "time sync not started: %s", esp_err_to_name(err));
        g_sntp_started = false;
    }
}

void reconnect(void *) { esp_wifi_connect(); }

void schedule_reconnect()
{
    if (g_reconnect_paused) {
        g_reconnect_pending = true;  // resumed when the access point stops
        return;
    }
    const uint32_t delay_ms = g_backoff.next_ms();
    ESP_LOGI(kTag, "next connection attempt in %" PRIu32 " s", delay_ms / 1000);
    esp_timer_stop(g_reconnect_timer);  // in case one is pending; harmless otherwise
    esp_timer_start_once(g_reconnect_timer, static_cast<uint64_t>(delay_ms) * 1000);
}

void on_wifi_event(void *, esp_event_base_t, int32_t id, void *data)
{
    switch (id) {
    case WIFI_EVENT_STA_START:
        if (wifi_configured(g_settings)) {
            ESP_LOGI(kTag, "connecting to \"%s\"", g_settings.ssid.c_str());
            esp_wifi_connect();
        }
        break;
    case WIFI_EVENT_AP_STACONNECTED:
        ESP_LOGI(kTag, "setup network: a device joined");
        break;
    case WIFI_EVENT_STA_DISCONNECTED: {
        const auto *event = static_cast<const wifi_event_sta_disconnected_t *>(data);
        if (g_connected.exchange(false)) {
            ESP_LOGW(kTag, "disconnected (reason %u)", event->reason);
        } else {
            ESP_LOGW(kTag, "connection failed (reason %u)", event->reason);
        }
        schedule_reconnect();
        break;
    }
    default:
        break;
    }
}

void on_ip_event(void *, esp_event_base_t, int32_t id, void *data)
{
    if (id != IP_EVENT_STA_GOT_IP) {
        return;
    }
    const auto *event = static_cast<const ip_event_got_ip_t *>(data);
    g_connected = true;
    g_backoff.reset();

    wifi_ap_record_t ap{};
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        ESP_LOGI(kTag, "connected as %s, IP " IPSTR ", channel %u, signal %d dBm", g_hostname.data(),
                 IP2STR(&event->ip_info.ip), ap.primary, ap.rssi);
    } else {
        ESP_LOGI(kTag, "connected as %s, IP " IPSTR, g_hostname.data(), IP2STR(&event->ip_info.ip));
    }
    start_sntp();
}

}  // namespace

NetSettings default_settings()
{
    NetSettings s;
    s.ssid.set(CONFIG_CLIMASENSE_WIFI_SSID);
    s.password.set(CONFIG_CLIMASENSE_WIFI_PASSWORD);
    s.country.set(CONFIG_CLIMASENSE_WIFI_COUNTRY);
    s.sntp_server.set(CONFIG_CLIMASENSE_SNTP_SERVER);
    s.timezone.set(CONFIG_CLIMASENSE_TIMEZONE);
    return s;
}

esp_err_t start(const NetSettings &settings)
{
    if (const auto problem = validate(settings)) {
        ESP_LOGE(kTag, "network settings not usable: %s", to_string(*problem));
        return ESP_ERR_INVALID_ARG;
    }
    g_settings = settings;

    ESP_RETURN_ON_ERROR(esp_netif_init(), kTag, "netif init");
    if (const esp_err_t err = esp_event_loop_create_default(); err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;  // ESP_ERR_INVALID_STATE: the loop exists already, which is fine
    }
    g_netif = esp_netif_create_default_wifi_sta();
    ESP_RETURN_ON_FALSE(g_netif != nullptr, ESP_FAIL, kTag, "create station interface");

    ESP_RETURN_ON_ERROR(esp_netif_set_hostname(g_netif, device_id()), kTag, "host name");

    const wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), kTag, "wifi init");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, nullptr), kTag,
                        "wifi events");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip_event, nullptr), kTag,
                        "ip events");

    esp_timer_create_args_t timer{};
    timer.callback = reconnect;
    timer.name = "wifi_reconnect";
    ESP_RETURN_ON_ERROR(esp_timer_create(&timer, &g_reconnect_timer), kTag, "reconnect timer");

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), kTag, "station mode");
    // Country as configured, not taken over from the access point.
    ESP_RETURN_ON_ERROR(esp_wifi_set_country_code(g_settings.country.c_str(), false), kTag, "country %s",
                        g_settings.country.c_str());

    // The radio starts even without a configured network: the setup portal needs it.
    wifi_config_t config{};
    std::memcpy(config.sta.ssid, g_settings.ssid.c_str(), g_settings.ssid.view().size());
    std::memcpy(config.sta.password, g_settings.password.c_str(), g_settings.password.view().size());
    config.sta.threshold.authmode = g_settings.password.empty() ? WIFI_AUTH_OPEN : WIFI_AUTH_WPA2_PSK;
    config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;  // WPA3 where the router offers it
    config.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    config.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;  // the strongest of several access points
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), kTag, "station config");

    // Power save stays at ESP-IDF's default (modem sleep): less radio time, less heat.
    ESP_RETURN_ON_ERROR(esp_wifi_start(), kTag, "wifi start");
    g_wifi_started = true;
    if (wifi_configured(g_settings)) {
        ESP_LOGI(kTag, "started as %s, country %s", device_id(), g_settings.country.c_str());
    } else {
        ESP_LOGW(kTag, "started as %s, but no network is configured", device_id());
    }
    return ESP_OK;
}

const char *device_id()
{
    if (g_hostname[0] == '\0') {
        uint8_t mac[6] = {};
        esp_read_mac(mac, ESP_MAC_WIFI_STA);  // from eFuse; cannot fail for the station MAC
        g_hostname = hostname_from_mac(mac);
    }
    return g_hostname.data();
}

bool connected() { return g_connected; }

bool time_synced() { return g_time_synced; }

esp_err_t start_access_point(const char *ssid, std::array<uint8_t, 4> &ip)
{
    ESP_RETURN_ON_FALSE(g_wifi_started, ESP_ERR_INVALID_STATE, kTag, "Wi-Fi not started");
    if (g_ap_netif == nullptr) {
        g_ap_netif = esp_netif_create_default_wifi_ap();
        ESP_RETURN_ON_FALSE(g_ap_netif != nullptr, ESP_FAIL, kTag, "create access point interface");
    }
    g_reconnect_paused = true;
    esp_timer_stop(g_reconnect_timer);

    wifi_config_t config{};
    const std::size_t length = std::min(std::strlen(ssid), sizeof(config.ap.ssid));
    std::memcpy(config.ap.ssid, ssid, length);
    config.ap.ssid_len = static_cast<uint8_t>(length);
    config.ap.authmode = WIFI_AUTH_OPEN;  // decided: open, only while setup mode is on
    config.ap.max_connection = 4;
    wifi_ap_record_t sta{};
    config.ap.channel = (g_connected && esp_wifi_sta_get_ap_info(&sta) == ESP_OK) ? sta.primary : 1;
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_APSTA), kTag, "station + access point mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_AP, &config), kTag, "access point config");

    esp_netif_ip_info_t info{};
    ESP_RETURN_ON_ERROR(esp_netif_get_ip_info(g_ap_netif, &info), kTag, "access point address");
    const uint32_t addr = info.ip.addr;  // network byte order: the first octet is the lowest byte
    ip = {static_cast<uint8_t>(addr), static_cast<uint8_t>(addr >> 8), static_cast<uint8_t>(addr >> 16),
          static_cast<uint8_t>(addr >> 24)};

    // DHCP option 114 (RFC 8910): tells newer phones where the portal is, besides the DNS redirect.
    snprintf(g_portal_uri, sizeof(g_portal_uri), "http://%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
    esp_netif_dhcps_stop(g_ap_netif);
    esp_netif_dhcps_option(g_ap_netif, ESP_NETIF_OP_SET, ESP_NETIF_CAPTIVEPORTAL_URI, g_portal_uri,
                           std::strlen(g_portal_uri));
    esp_netif_dhcps_start(g_ap_netif);

    ESP_LOGI(kTag, "setup network \"%s\" on channel %u, portal %s", ssid, config.ap.channel, g_portal_uri);
    return ESP_OK;
}

void stop_access_point()
{
    if (!g_wifi_started) {
        return;
    }
    esp_wifi_set_mode(WIFI_MODE_STA);
    g_reconnect_paused = false;
    if (wifi_configured(g_settings) && !g_connected && g_reconnect_pending.exchange(false)) {
        esp_wifi_connect();
    }
    ESP_LOGI(kTag, "setup network closed");
}

std::vector<AccessPoint> scan()
{
    std::vector<AccessPoint> found;
    if (!g_wifi_started) {
        return found;
    }
    wifi_scan_config_t config{};  // all channels, hidden networks not shown
    esp_err_t err = esp_wifi_scan_start(&config, true);
    if (err == ESP_ERR_WIFI_STATE) {
        // The station is in the middle of a connection attempt; give it a moment.
        vTaskDelay(pdMS_TO_TICKS(1500));
        err = esp_wifi_scan_start(&config, true);
    }
    if (err != ESP_OK) {
        ESP_LOGW(kTag, "scan failed: %s", esp_err_to_name(err));
        return found;
    }
    uint16_t count = 32;
    static std::array<wifi_ap_record_t, 32> records;  // ~3 KB: kept off the caller's stack
    if (esp_wifi_scan_get_ap_records(&count, records.data()) != ESP_OK) {
        return found;
    }
    for (uint16_t i = 0; i < count; ++i) {
        const auto &r = records[i];
        const auto *name = reinterpret_cast<const char *>(r.ssid);
        found.push_back({std::string(name, strnlen(name, sizeof(r.ssid))), r.rssi, r.authmode != WIFI_AUTH_OPEN});
    }
    ESP_LOGI(kTag, "scan: %u networks", count);
    return tidy_networks(std::move(found));
}

}  // namespace net
