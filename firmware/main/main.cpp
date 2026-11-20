// ClimaSense firmware entry point.
// Report the previous run (its last log lines, a crash dump), bring up the rails, LED and button,
// start the sensor task (sensors/sensor_task.h), Wi-Fi with network time (net/wifi.h) and, when
// needed, the setup portal (portal/portal.h). At start the LED shows red, green, blue and white
// in turn (a check of the LED and its colour balance); a long press opens the setup portal, a
// short press closes it, or otherwise cycles through the LED colours.

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstddef>

#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_err.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board/board.h"
#include "board/button.h"
#include "board/led.h"
#include "diagnostics/diagnostics.h"
#include "net/wifi.h"
#include "portal/portal.h"
#include "settings/nvs_store.h"
#include "settings/store.h"
#include "sensors/sensor_task.h"

namespace {

constexpr const char *kTag = "climasense";
constexpr int64_t kHeartbeatPeriodUs = 5'000'000;
constexpr uint8_t kBrightness = 128;
constexpr int64_t kBlinkHalfPeriodUs = 250'000;

struct NamedColour {
    const char *name;
    board::Rgb rgb;
};

constexpr std::array kColours{
    NamedColour{"off", board::colour::kOff},
    NamedColour{"red", board::colour::kRed},
    NamedColour{"green", board::colour::kGreen},
    NamedColour{"blue", board::colour::kBlue},
    NamedColour{"white", board::colour::kWhite},
};

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

void led_self_test()
{
    for (std::size_t i = 1; i < kColours.size(); ++i) {
        board::led::set(kColours[i].rgb, kBrightness);
        vTaskDelay(pdMS_TO_TICKS(400));
    }
    board::led::off();
}

}  // namespace

extern "C" void app_main()
{
    diagnostics::init();
    log_banner();
    diagnostics::report_previous_boot();

    ESP_ERROR_CHECK(board::init());
    ESP_ERROR_CHECK(board::led::init());
    ESP_ERROR_CHECK(board::button::init());
    ESP_ERROR_CHECK(sensors::start_task());
    ESP_ERROR_CHECK(init_nvs());

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

    const esp_err_t wifi = net::start(network.value);
    if (wifi != ESP_OK) {
        ESP_LOGE(kTag, "Wi-Fi not started: %s", esp_err_to_name(wifi));  // the sensors keep running
    }
    led_self_test();

    // Setup mode (captive portal): on first boot, i.e. with no network configured, and on a long
    // press of the BOOT button; a short press closes it.
    static portal::Context portal_context;
    portal_context.store = &store;
    portal_context.net = network.value;
    portal_context.device = device.value;
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

    std::size_t colour_index = 0;
    int64_t next_heartbeat = esp_timer_get_time();
    int64_t next_blink = 0;
    bool blink_on = false;
    bool portal_was_open = false;

    for (;;) {
        const int64_t now = esp_timer_get_time();
        if (now >= next_heartbeat) {
            ESP_LOGI(kTag, "alive, uptime %" PRId64 " s, free heap %" PRIu32 " bytes",
                     now / 1'000'000, esp_get_free_heap_size());
            next_heartbeat += kHeartbeatPeriodUs;
        }

        // While setup mode is open, the LED blinks blue (twice a second).
        const bool portal_open = portal::is_open();
        if (portal_open && now >= next_blink) {
            blink_on = !blink_on;
            board::led::set(blink_on ? board::colour::kBlue : board::colour::kOff, kBrightness);
            next_blink = now + kBlinkHalfPeriodUs;
        } else if (!portal_open && portal_was_open) {
            board::led::off();  // closed by its timeout, the button or a restart
        }
        portal_was_open = portal_open;

        const int64_t until = portal_open ? std::min(next_heartbeat, next_blink) : next_heartbeat;
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
            // LED colour check (step 2): cycles through the colours.
            colour_index = (colour_index + 1) % kColours.size();
            ESP_LOGI(kTag, "short press: LED %s", kColours[colour_index].name);
            board::led::set(kColours[colour_index].rgb, kBrightness);
            break;
        case board::ButtonEvent::LongPress:
            ESP_LOGI(kTag, "long press: opening the setup portal");
            open_portal();
            break;
        }
    }
}
