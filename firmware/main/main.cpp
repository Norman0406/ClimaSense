// ClimaSense firmware entry point.
// Report the previous run (its last log lines, a crash dump), bring up the rails, LED and button,
// start the sensor task (sensors/sensor_task.h), Wi-Fi with network time (net/wifi.h) and, when
// needed, the setup portal (portal/portal.h), and publish the sensor values over MQTT every
// 60 s, with a boot report and WARNING-and-above log lines (telemetry/client.h). At start the LED
// shows red, green, blue and white in turn (a check of the LED and its colour balance), then the
// device's status (board/status_pattern.h). A long press opens the setup portal; a short press
// closes it, or otherwise shows the status for a few seconds (green: all well). The app task is
// watched by the task watchdog, and the device restarts after an hour offline (net/offline_guard.h).

#include <algorithm>
#include <cinttypes>
#include <cstddef>
#include <ctime>
#include <initializer_list>
#include <string>

#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_err.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board/board.h"
#include "board/button.h"
#include "board/led.h"
#include "board/status_pattern.h"
#include "diagnostics/diagnostics.h"
#include "net/offline_guard.h"
#include "net/wifi.h"
#include "ota/ota.h"
#include "portal/portal.h"
#include "telemetry/client.h"
#include "telemetry/payload.h"
#include "telemetry/rate_limit.h"
#include "settings/nvs_store.h"
#include "settings/store.h"
#include "sensors/sensor_task.h"

namespace {

constexpr const char *kTag = "climasense";
constexpr int64_t kHeartbeatPeriodUs = 5'000'000;
constexpr uint8_t kBrightness = 128;
constexpr int64_t kLogCheckPeriodUs = 1'000'000;
// How long a short press shows the status (green when all is well).
constexpr int64_t kShowStatusUs = 5'000'000;

void log_banner()
{
    const esp_app_desc_t *app = esp_app_get_description();
    esp_chip_info_t chip{};
    esp_chip_info(&chip);
    uint32_t flash_size = 0;
    esp_flash_get_size(nullptr, &flash_size);

    ESP_LOGI(kTag, "ClimaSense firmware %s (ESP-IDF %s, built %s %s)",
             app->version, app->idf_ver, app->date, app->time);
    ESP_LOGI(kTag, "chip revision v%d.%d, %d core(s), flash %" PRIu32 " MB",
             chip.revision / 100, chip.revision % 100, chip.cores, flash_size / (1024 * 1024));
    ESP_LOGI(kTag, "build %s, reset reason: %s", diagnostics::build_id(),
             diagnostics::reset_reason_name(esp_reset_reason()));
}

// NVS holds Wi-Fi's calibration data and, from step 7 on, the settings entered in the portal.
// A full or outdated NVS partition is erased and set up again, as ESP-IDF recommends.
esp_err_t init_nvs()
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(kTag, "NVS partition unusable (%s), erasing it", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    return err;
}

// Logs where a settings record came from.
template <typename Settings>
void log_loaded(const char *what, const settings::Loaded<Settings> &loaded)
{
    if (loaded.store_failed) {
        ESP_LOGE(kTag, "%s settings: storage unreadable, using build defaults", what);
    } else if (loaded.rejected) {
        ESP_LOGW(kTag, "%s settings: stored values invalid, using build defaults", what);
    } else if (loaded.stored_fields > 0) {
        ESP_LOGI(kTag, "%s settings: %u field(s) from storage, the rest build defaults", what,
                 static_cast<unsigned>(loaded.stored_fields));
    } else {
        ESP_LOGI(kTag, "%s settings: build defaults", what);
    }
}

// Current local time as RFC 3339, or empty while the clock is not set yet.
std::string local_time()
{
    if (!net::time_synced()) {
        return {};
    }
    const time_t now = time(nullptr);
    struct tm local {};
    localtime_r(&now, &local);
    char text[32];
    strftime(text, sizeof(text), "%Y-%m-%dT%H:%M:%S%z", &local);
    return telemetry::rfc3339_offset(text);
}

// Takes the sensor snapshot (which starts the next averaging window) and publishes it.
void publish(const std::string &display_name)
{
    const sensors::SensorSnapshot snapshot = sensors::take_snapshot();
    if (!telemetry::connected()) {
        return;  // the window still restarts: every message averages one interval
    }
    const std::string time = local_time();
    const telemetry::StateMeta meta{net::device_id(), display_name, time, net::rssi(),
                                    static_cast<uint32_t>(esp_timer_get_time() / 1'000'000)};
    const std::string json = telemetry::state_json(snapshot, meta);
    if (telemetry::publish_state(json)) {
        ESP_LOGD(kTag, "published: %s", json.c_str());
    }
}

// The boot report: what the last run left behind (reset reason, its last log lines, a crash).
std::string boot_report(const std::string &display_name)
{
    telemetry::BootInfo info;
    info.device_id = net::device_id();
    info.name = display_name;
    info.firmware_version = esp_app_get_description()->version;
    info.build_id = diagnostics::build_id();
    info.reset_reason = diagnostics::reset_reason_name(esp_reset_reason());
    info.previous_log = diagnostics::previous_log();
    info.on_trial = ota::on_trial();
    const auto crash = diagnostics::crash_summary();
    if (crash) {
        info.crash = telemetry::CrashInfo{crash->reason, crash->task,  crash->pc,         crash->mcause,
                                          crash->mtval,  crash->ra,    crash->sp,         crash->build,
                                          crash->this_build, crash->from_this_reset};
    }
    return telemetry::boot_json(info);
}

// Log lines over MQTT, at most 10 a minute; what does not fit is counted and reported in one note.
telemetry::RateLimiter g_log_limit(10, 60);
uint32_t g_log_suppressed = 0;

void forward_log_lines()
{
    if (!telemetry::connected()) {
        return;  // the queue keeps up to 16 lines for when the connection is back
    }
    const auto now_s = static_cast<uint32_t>(esp_timer_get_time() / 1'000'000);
    while (const auto line = diagnostics::next_forwarded_line()) {
        if (g_log_limit.allow(now_s)) {
            telemetry::publish_log(telemetry::log_json(*line));
        } else {
            ++g_log_suppressed;
        }
    }
    g_log_suppressed += diagnostics::take_dropped_forward_lines();
    if (g_log_suppressed > 0 && g_log_limit.allow(now_s)) {
        telemetry::publish_log(telemetry::dropped_log_json(g_log_suppressed));
        g_log_suppressed = 0;
    }
}

void led_self_test()
{
    for (const board::Rgb rgb : {board::colour::kRed, board::colour::kGreen, board::colour::kBlue, board::colour::kWhite}) {
        board::led::set(rgb, kBrightness);
        vTaskDelay(pdMS_TO_TICKS(400));
    }
    board::led::off();
}

// The status LED (board/status_pattern.h): plays the pattern of the current status, from its
// start whenever the status changes. Only the app task drives the LED.
class StatusLed {
public:
    // Updates the LED; returns when it next needs a look (esp_timer time, us).
    int64_t update(board::Status status, bool show_ok, int64_t now)
    {
        if (status != status_ || show_ok != show_ok_) {
            if (status != status_) {
                ESP_LOGI(kTag, "status: %s", board::to_string(status));
            }
            status_ = status;
            show_ok_ = show_ok;
            since_ = now;
        }
        const auto elapsed_ms = static_cast<uint32_t>((now - since_) / 1000);
        const board::LedStep step = board::status_led(status_, elapsed_ms, show_ok_);
        if (!shown_ || step.colour.r != shown_colour_.r || step.colour.g != shown_colour_.g ||
            step.colour.b != shown_colour_.b) {
            board::led::set(step.colour, kBrightness);
            shown_colour_ = step.colour;
            shown_ = true;
        }
        return now + static_cast<int64_t>(step.hold_ms) * 1000;
    }

private:
    board::Status status_ = board::Status::Ok;
    bool show_ok_ = false;
    int64_t since_ = 0;
    board::Rgb shown_colour_{};
    bool shown_ = false;
};

}  // namespace

extern "C" void app_main()
{
    diagnostics::init();
    log_banner();
    diagnostics::report_previous_boot();

    ESP_ERROR_CHECK(board::init());
    ESP_ERROR_CHECK(board::led::init());
    ESP_ERROR_CHECK(board::button::init());
    ESP_ERROR_CHECK(init_nvs());  // before the sensor task, which keeps the VOC baseline in NVS
    ESP_ERROR_CHECK(sensors::start_task());

    // Settings: stored ones (from the portal, step 7) take precedence over the build defaults.
    static settings::NvsStore store;
    if (const esp_err_t err = store.open(); err != ESP_OK) {
        ESP_LOGE(kTag, "settings storage not available: %s", esp_err_to_name(err));
    }
    const auto device = settings::load_device(store, settings::DeviceSettings{});
    log_loaded("device", device);
    ESP_LOGI(kTag, "device %s, name \"%.*s\"", net::device_id(),
             static_cast<int>(settings::display_name(device.value, net::device_id()).size()),
             settings::display_name(device.value, net::device_id()).data());
    const auto network = settings::load_net(store, net::default_settings());
    log_loaded("network", network);
    const auto mqtt = settings::load_mqtt(store, telemetry::default_settings());
    log_loaded("MQTT", mqtt);

    const esp_err_t wifi = net::start(network.value);
    if (wifi != ESP_OK) {
        ESP_LOGE(kTag, "Wi-Fi not started: %s", esp_err_to_name(wifi));  // the sensors keep running
    }
    const std::string display_name(settings::display_name(device.value, net::device_id()));
    if (!telemetry::mqtt_configured(mqtt.value)) {
        diagnostics::set_forward_level(diagnostics::LogLevel::None);  // nowhere to send them
    }
    telemetry::set_boot_report(boot_report(display_name));
    bool dump_erased = false;
    // After an update, the new firmware is on trial until it has shown it works (ota/logic.h).
    bool on_trial = ota::on_trial();
    if (on_trial) {
        ESP_LOGW(kTag, "firmware %s is on trial after an update", esp_app_get_description()->version);
    }
    if (wifi == ESP_OK) {
        const telemetry::Identity identity{net::device_id(), display_name, esp_app_get_description()->version};
        if (const esp_err_t err = telemetry::start(mqtt.value, identity); err != ESP_OK) {
            ESP_LOGE(kTag, "MQTT not started: %s", esp_err_to_name(err));
        }
    }
    led_self_test();

    // Setup mode (captive portal): on first boot, i.e. with no network configured, and on a long
    // press of the BOOT button; a short press closes it.
    static portal::Context portal_context;
    portal_context.store = &store;
    portal_context.net = network.value;
    portal_context.device = device.value;
    portal_context.mqtt = mqtt.value;
    portal_context.mqtt_connected = telemetry::connected;
    portal_context.firmware_version = esp_app_get_description()->version;
    portal_context.build_id = diagnostics::build_id();
    const auto open_portal = [] {
        if (const esp_err_t err = portal::open(portal_context); err != ESP_OK) {
            ESP_LOGE(kTag, "setup portal not opened: %s", esp_err_to_name(err));
        }
    };
    if (wifi == ESP_OK && !net::wifi_configured(network.value)) {
        open_portal();
    }

    int64_t next_heartbeat = esp_timer_get_time();
    // The first message after one full interval, so it averages a full minute of readings.
    int64_t next_publish = esp_timer_get_time() + static_cast<int64_t>(telemetry::kPublishIntervalS) * 1'000'000;
    int64_t next_log_check = 0;
    int64_t show_status_until = 0;
    StatusLed status_led;
    net::OfflineGuard offline_guard;

    // From here on, the task watchdog restarts the device (with a core dump) if this loop hangs
    // for longer than CONFIG_ESP_TASK_WDT_TIMEOUT_S.
    ESP_ERROR_CHECK(esp_task_wdt_add(nullptr));

    for (;;) {
        esp_task_wdt_reset();
        const int64_t now = esp_timer_get_time();
        if (now >= next_heartbeat) {
            ESP_LOGI(kTag, "alive, uptime %" PRId64 " s, free heap %" PRIu32 " bytes",
                     now / 1'000'000, esp_get_free_heap_size());
            next_heartbeat += kHeartbeatPeriodUs;
        }

        if (now >= next_log_check) {
            forward_log_lines();
            if (const auto level = telemetry::take_log_level_request()) {
                diagnostics::set_forward_level(*level);
                ESP_LOGI(kTag, "log lines over MQTT from level %c on (until restart)",
                         *level == diagnostics::LogLevel::None ? '-' : diagnostics::level_letter(*level));
            }
            // The core dump stays in flash until the boot report that carries it is delivered.
            if (!dump_erased && telemetry::boot_report_delivered() && diagnostics::has_crash_dump()) {
                if (diagnostics::erase_crash_dump() == ESP_OK) {
                    ESP_LOGI(kTag, "core dump reported over MQTT and erased");
                }
                dump_erased = true;
            }
            // An update command over MQTT.
            if (const auto request = telemetry::take_update_request()) {
                if (const auto command = ota::parse_update_command(*request)) {
                    ota::start_from_url(*command, telemetry::publish_update_status);
                } else {
                    telemetry::publish_update_status(ota::status_json(
                        "refused", std::nullopt, "expected \"<http(s) URL>\" or \"<URL> force\""));
                }
            }
            const auto uptime_s = static_cast<uint32_t>(now / 1'000'000);
            const bool healthy = ota::trial_healthy(telemetry::mqtt_configured(mqtt.value), telemetry::connected(),
                                                    net::wifi_configured(network.value), net::connected());
            if (offline_guard.restart_due(uptime_s, healthy, portal::is_open() || ota::busy())) {
                ESP_LOGE(kTag, "offline for %u minutes; restarting",
                         static_cast<unsigned>(net::OfflineGuard::kRestartAfterS / 60));
                esp_restart();
            }
            if (on_trial) {
                switch (ota::TrialGuard{}.check(uptime_s, healthy)) {
                case ota::TrialGuard::Verdict::Accept:
                    ota::accept();
                    on_trial = false;
                    break;
                case ota::TrialGuard::Verdict::Reject:
                    ota::reject();  // restarts into the previous firmware
                    break;
                case ota::TrialGuard::Verdict::Wait:
                    break;
                }
            }
            next_log_check = now + kLogCheckPeriodUs;
        }

        if (now >= next_publish) {
            publish(display_name);
            next_publish += static_cast<int64_t>(telemetry::kPublishIntervalS) * 1'000'000;
        }

        board::StatusInputs status;
        status.updating = ota::busy();
        status.setup_open = portal::is_open();
        status.wifi_connected = net::connected();
        status.broker_configured = telemetry::mqtt_configured(mqtt.value);
        status.broker_connected = telemetry::connected();
        status.sensors_working = sensors::working();
        const int64_t next_led = status_led.update(board::pick_status(status), now < show_status_until, now);

        int64_t until = std::min({next_heartbeat, next_publish, next_log_check, next_led});
        if (show_status_until > now) {
            until = std::min(until, show_status_until);
        }
        const TickType_t wait = pdMS_TO_TICKS(std::max<int64_t>(until - now, 0) / 1000) + 1;
        const auto event = board::button::wait(wait);
        if (!event) {
            continue;
        }
        switch (*event) {
        case board::ButtonEvent::ShortPress:
            if (portal::is_open()) {
                ESP_LOGI(kTag, "short press: closing the setup portal");
                portal::close();
                break;
            }
            ESP_LOGI(kTag, "short press: showing the status");
            show_status_until = esp_timer_get_time() + kShowStatusUs;
            break;
        case board::ButtonEvent::LongPress:
            ESP_LOGI(kTag, "long press: opening the setup portal");
            open_portal();
            break;
        }
    }
}
