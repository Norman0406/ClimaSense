// ClimaSense firmware entry point.
// Step 3 plus diagnostics: report the previous run (its last log lines, a crash dump), bring up
// the rails, LED and button, and start the sensor task, which scans the sensor bus once (see
// sensors/sensor_task.h). At start the LED shows red, green, blue and white in turn (a check of
// the LED and its colour balance); a short press then cycles through the colours, a long press
// shows blue (later: Wi-Fi setup portal).

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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board/board.h"
#include "board/button.h"
#include "board/led.h"
#include "diagnostics/diagnostics.h"
#include "sensors/sensor_task.h"

namespace {

constexpr const char *kTag = "climasense";
constexpr int64_t kHeartbeatPeriodUs = 5'000'000;
constexpr uint8_t kBrightness = 128;

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
    led_self_test();

    std::size_t colour_index = 0;
    int64_t next_heartbeat = esp_timer_get_time();

    for (;;) {
        const int64_t now = esp_timer_get_time();
        if (now >= next_heartbeat) {
            ESP_LOGI(kTag, "alive, uptime %" PRId64 " s, free heap %" PRIu32 " bytes",
                     now / 1'000'000, esp_get_free_heap_size());
            next_heartbeat += kHeartbeatPeriodUs;
        }

        const TickType_t wait = pdMS_TO_TICKS((next_heartbeat - now) / 1000) + 1;
        const auto event = board::button::wait(wait);
        if (!event) {
            continue;
        }
        switch (*event) {
        case board::ButtonEvent::ShortPress:
            colour_index = (colour_index + 1) % kColours.size();
            ESP_LOGI(kTag, "short press: LED %s", kColours[colour_index].name);
            board::led::set(kColours[colour_index].rgb, kBrightness);
            break;
        case board::ButtonEvent::LongPress:
            ESP_LOGI(kTag, "long press: Wi-Fi setup portal goes here (step 7)");
            board::led::set(board::colour::kBlue, kBrightness);
            break;
        }
    }
}
