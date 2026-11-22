#include "telemetry/client.h"

#include <atomic>
#include <string_view>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif_types.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "mqtt_client.h"
#include "sdkconfig.h"

#include "net/backoff.h"
#include "telemetry/payload.h"

namespace telemetry {

namespace {

constexpr const char *kTag = "mqtt";

MqttSettings g_settings;  // kept for the life of the program: the client keeps the pointers
Identity g_identity;
std::string g_state_topic;
std::string g_status_topic;
std::string g_ha_status_topic;
esp_mqtt_client_handle_t g_client = nullptr;
std::atomic<bool> g_connected{false};
std::string g_boot_topic;
std::string g_log_topic;
std::string g_log_level_topic;
std::string g_boot_report;            // set before start(), then only read
std::atomic<int> g_boot_msg_id{-1};
std::atomic<bool> g_boot_delivered{false};
std::atomic<int> g_log_level_request{-1};  // a diagnostics::LogLevel, or -1
std::string g_update_topic;
std::string g_update_status_topic;
portMUX_TYPE g_update_lock = portMUX_INITIALIZER_UNLOCKED;
std::string g_update_request;  // under g_update_lock
bool g_update_requested = false;

// Reconnecting is ours, not the client's: after a lost connection or a failed attempt, the next
// attempt follows after 1, 2, 4 ... 60 s (net/backoff.h), and at once when Wi-Fi has a new
// address. The client's own fixed 10 s retry is switched off.
esp_timer_handle_t g_reconnect_timer = nullptr;
portMUX_TYPE g_backoff_lock = portMUX_INITIALIZER_UNLOCKED;
net::ReconnectBackoff g_backoff;  // under g_backoff_lock
std::atomic<bool> g_outage_logged{false};

// The broker's acknowledgement of the last state message. The ack can in principle arrive before
// publish_state() has stored the message ID, so an ack for an unknown ID is kept as well.
std::atomic<int> g_state_msg_id{-1};
std::atomic<bool> g_state_acked{false};
std::atomic<int> g_other_ack_id{-1};

void reconnect(void *)
{
    // Refused unless the client is waiting to reconnect, e.g. when an attempt is already running.
    esp_mqtt_client_reconnect(g_client);
}

void schedule_reconnect()
{
    taskENTER_CRITICAL(&g_backoff_lock);
    const uint32_t delay_ms = g_backoff.next_ms();
    taskEXIT_CRITICAL(&g_backoff_lock);
    ESP_LOGD(kTag, "next connection attempt in %u s", static_cast<unsigned>(delay_ms / 1000));
    esp_timer_stop(g_reconnect_timer);  // in case one is pending; harmless otherwise
    esp_timer_start_once(g_reconnect_timer, static_cast<uint64_t>(delay_ms) * 1000);
}

void reset_backoff()
{
    taskENTER_CRITICAL(&g_backoff_lock);
    g_backoff.reset();
    taskEXIT_CRITICAL(&g_backoff_lock);
}

// Wi-Fi has a (new) address: the broker is worth trying at once.
void on_got_ip(void *, esp_event_base_t, int32_t, void *)
{
    if (g_connected) {
        return;
    }
    reset_backoff();
    esp_timer_stop(g_reconnect_timer);
    esp_mqtt_client_reconnect(g_client);
}

void publish_discovery()
{
    const auto messages = discovery_messages({g_settings.ha_prefix.view(), g_settings.base_topic.view(),
                                              g_identity.device_id, g_identity.name, g_identity.firmware_version});
    for (const auto &m : messages) {
        esp_mqtt_client_enqueue(g_client, m.topic.c_str(), m.payload.data(), static_cast<int>(m.payload.size()), 1,
                                1, true);
    }
    ESP_LOGI(kTag, "Home Assistant discovery: %u messages queued", static_cast<unsigned>(messages.size()));
}

void on_event(void *, esp_event_base_t, int32_t id, void *data)
{
    const auto *event = static_cast<const esp_mqtt_event_t *>(data);
    switch (static_cast<esp_mqtt_event_id_t>(id)) {
    case MQTT_EVENT_CONNECTED:
        g_connected = true;
        g_outage_logged = false;
        reset_backoff();
        esp_timer_stop(g_reconnect_timer);
        ESP_LOGI(kTag, "connected to %s:%u", g_settings.host.c_str(), g_settings.port);
        esp_mqtt_client_enqueue(g_client, g_status_topic.c_str(), kOnline.data(), static_cast<int>(kOnline.size()), 1,
                                1, true);
        if (g_settings.ha_discovery) {
            esp_mqtt_client_subscribe_single(g_client, g_ha_status_topic.c_str(), 1);
            publish_discovery();
        }
        esp_mqtt_client_subscribe_single(g_client, g_log_level_topic.c_str(), 1);
        esp_mqtt_client_subscribe_single(g_client, g_update_topic.c_str(), 1);
        if (!g_boot_report.empty() && !g_boot_delivered) {
            g_boot_msg_id = esp_mqtt_client_enqueue(g_client, g_boot_topic.c_str(), g_boot_report.data(),
                                                    static_cast<int>(g_boot_report.size()), 1, 1, true);
        }
        break;
    case MQTT_EVENT_PUBLISHED:
        if (event->msg_id >= 0 && event->msg_id == g_boot_msg_id) {
            g_boot_delivered = true;
            ESP_LOGI(kTag, "boot report delivered");
        } else if (event->msg_id > 0 && event->msg_id == g_state_msg_id) {
            g_state_acked = true;
        } else {
            g_other_ack_id = event->msg_id;
        }
        break;
    case MQTT_EVENT_DISCONNECTED:
        // After a lost connection and after every failed attempt.
        if (g_connected.exchange(false)) {
            ESP_LOGW(kTag, "disconnected; reconnecting in the background");
        }
        schedule_reconnect();
        break;
    case MQTT_EVENT_DATA: {
        // Home Assistant announces "online" on its status topic after a restart: discovery again.
        const std::string_view topic(event->topic, static_cast<std::size_t>(event->topic_len));
        const std::string_view payload(event->data, static_cast<std::size_t>(event->data_len));
        if (g_settings.ha_discovery && topic == g_ha_status_topic && payload == "online") {
            publish_discovery();
        } else if (topic == g_update_topic && !event->retain) {
            // A retained command would update again after every restart; such ones are ignored.
            std::string request(payload);
            taskENTER_CRITICAL(&g_update_lock);
            g_update_request.swap(request);
            g_update_requested = true;
            taskEXIT_CRITICAL(&g_update_lock);
        } else if (topic == g_log_level_topic) {
            if (const auto level = diagnostics::parse_level_name(payload)) {
                g_log_level_request = static_cast<int>(*level);
            } else {
                ESP_LOGW(kTag, "unknown log level \"%.*s\" (none, error, warn, info, debug)",
                         static_cast<int>(payload.size()), payload.data());
            }
        }
        break;
    }
    case MQTT_EVENT_ERROR:
        // Once per outage; the attempts after it come every 1 ... 60 s.
        if (!g_outage_logged.exchange(true)) {
            ESP_LOGW(kTag, "connection error (broker %s:%u); retrying in the background", g_settings.host.c_str(),
                     g_settings.port);
        }
        break;
    default:
        break;
    }
}

}  // namespace

MqttSettings default_settings()
{
    MqttSettings s;
    s.host.set(CONFIG_CLIMASENSE_MQTT_HOST);
    s.port = static_cast<uint16_t>(CONFIG_CLIMASENSE_MQTT_PORT);
    s.username.set(CONFIG_CLIMASENSE_MQTT_USERNAME);
    s.password.set(CONFIG_CLIMASENSE_MQTT_PASSWORD);
    s.base_topic.set(CONFIG_CLIMASENSE_MQTT_BASE_TOPIC);
#ifdef CONFIG_CLIMASENSE_MQTT_HA_DISCOVERY
    s.ha_discovery = true;
#endif
    s.ha_prefix.set(CONFIG_CLIMASENSE_MQTT_HA_PREFIX);
    return s;
}

esp_err_t start(const MqttSettings &settings, const Identity &identity)
{
    if (const auto problem = validate(settings)) {
        ESP_LOGE(kTag, "MQTT settings not usable: %s", to_string(*problem));
        return ESP_ERR_INVALID_ARG;
    }
    if (!mqtt_configured(settings)) {
        ESP_LOGW(kTag, "no broker configured; values are not sent");
        return ESP_OK;
    }
    ESP_RETURN_ON_FALSE(g_client == nullptr, ESP_ERR_INVALID_STATE, kTag, "already started");
    g_settings = settings;
    g_identity = identity;
    g_state_topic = state_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_status_topic = status_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_ha_status_topic = ha_status_topic(g_settings.ha_prefix.view());
    g_boot_topic = boot_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_log_topic = log_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_log_level_topic = log_level_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_update_topic = update_topic(g_settings.base_topic.view(), g_identity.device_id);
    g_update_status_topic = update_status_topic(g_settings.base_topic.view(), g_identity.device_id);

    esp_mqtt_client_config_t config{};
    config.broker.address.hostname = g_settings.host.c_str();
    config.broker.address.port = g_settings.port;
    config.broker.address.transport = MQTT_TRANSPORT_OVER_TCP;  // plain, decided 2026-11-20
    config.credentials.client_id = g_identity.device_id.c_str();
    if (!g_settings.username.empty()) {
        config.credentials.username = g_settings.username.c_str();
        if (!g_settings.password.empty()) {
            config.credentials.authentication.password = g_settings.password.c_str();
        }
    }
    config.session.last_will.topic = g_status_topic.c_str();
    config.session.last_will.msg = kOffline.data();
    config.session.last_will.msg_len = static_cast<int>(kOffline.size());
    config.session.last_will.qos = 1;
    config.session.last_will.retain = 1;
    config.session.keepalive = 60;  // the broker notices a vanished device within about 90 s
    config.buffer.size = 4096;      // the boot report carries up to 2 KB of log
    config.network.disable_auto_reconnect = true;  // reconnect() and schedule_reconnect() above

    esp_timer_create_args_t timer{};
    timer.callback = reconnect;
    timer.name = "mqtt_reconnect";
    ESP_RETURN_ON_ERROR(esp_timer_create(&timer, &g_reconnect_timer), kTag, "reconnect timer");

    g_client = esp_mqtt_client_init(&config);
    ESP_RETURN_ON_FALSE(g_client != nullptr, ESP_FAIL, kTag, "client init");
    ESP_RETURN_ON_ERROR(esp_mqtt_client_register_event(g_client, MQTT_EVENT_ANY, on_event, nullptr), kTag, "events");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_got_ip, nullptr), kTag,
                        "ip events");
    ESP_RETURN_ON_ERROR(esp_mqtt_client_start(g_client), kTag, "client start");
    ESP_LOGI(kTag, "publishing to %s every %u s (broker %s:%u%s)", g_state_topic.c_str(),
             static_cast<unsigned>(kPublishIntervalS), g_settings.host.c_str(), g_settings.port,
             g_settings.ha_discovery ? ", Home Assistant discovery on" : "");
    return ESP_OK;
}

bool connected() { return g_connected; }

void set_boot_report(std::string json) { g_boot_report = std::move(json); }

bool boot_report_delivered() { return g_boot_delivered; }

bool publish_log(const std::string &json)
{
    if (!g_connected || g_client == nullptr) {
        return false;
    }
    return esp_mqtt_client_enqueue(g_client, g_log_topic.c_str(), json.data(), static_cast<int>(json.size()), 0, 0,
                                   true) >= 0;
}

std::optional<std::string> take_update_request()
{
    std::string request;
    bool requested = false;
    taskENTER_CRITICAL(&g_update_lock);
    if (g_update_requested) {
        request.swap(g_update_request);
        g_update_requested = false;
        requested = true;
    }
    taskEXIT_CRITICAL(&g_update_lock);
    if (!requested) {
        return std::nullopt;
    }
    return request;
}

bool publish_update_status(const std::string &json)
{
    if (!g_connected || g_client == nullptr) {
        return false;
    }
    return esp_mqtt_client_enqueue(g_client, g_update_status_topic.c_str(), json.data(),
                                   static_cast<int>(json.size()), 1, 0, true) >= 0;
}

std::optional<diagnostics::LogLevel> take_log_level_request()
{
    const int level = g_log_level_request.exchange(-1);
    if (level < 0) {
        return std::nullopt;
    }
    return static_cast<diagnostics::LogLevel>(level);
}

bool publish_state(const std::string &json)
{
    if (!g_connected || g_client == nullptr) {
        return false;
    }
    g_state_acked = false;
    g_state_msg_id = -1;
    // QoS 1: the broker's ack tells the status LED that the values arrived (decided 2026-11-22).
    const int id = esp_mqtt_client_enqueue(g_client, g_state_topic.c_str(), json.data(),
                                           static_cast<int>(json.size()), 1, 0, true);
    g_state_msg_id = id;
    return id >= 0;
}

bool state_delivered()
{
    const int id = g_state_msg_id;
    return id > 0 && (g_state_acked || g_other_ack_id == id);
}

}  // namespace telemetry
