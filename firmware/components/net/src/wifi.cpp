#include "net/wifi.h"

#include <algorithm>
#include <atomic>
#include <cinttypes>
#include <cstdlib>
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
    const uint32_t delay_ms = g_backoff.next_ms();
    ESP_LOGI(kTag, "next connection attempt in %" PRIu32 " s", delay_ms / 1000);
    esp_timer_stop(g_reconnect_timer);  // in case one is pending; harmless otherwise
    esp_timer_start_once(g_reconnect_timer, static_cast<uint64_t>(delay_ms) * 1000);
}

void on_wifi_event(void *, esp_event_base_t, int32_t id, void *data)
{
    switch (id) {
    case WIFI_EVENT_STA_START:
        ESP_LOGI(kTag, "connecting to \"%s\"", g_settings.ssid.c_str());
        esp_wifi_connect();
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
    if (!wifi_configured(settings)) {
        ESP_LOGW(kTag, "no Wi-Fi network configured; Wi-Fi stays off");
        return ESP_OK;
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
    ESP_LOGI(kTag, "started as %s, country %s", g_hostname.data(), g_settings.country.c_str());
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

}  // namespace net
