// ClimaSense firmware entry point.
// Step 1 (skeleton): print a start-up banner and a periodic heartbeat over the native USB console.

#include <cinttypes>

#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board.h"

namespace {

constexpr const char *kTag = "climasense";
constexpr TickType_t kHeartbeatPeriod = pdMS_TO_TICKS(5000);

constexpr const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
    case ESP_RST_POWERON:   return "power-on";
    case ESP_RST_EXT:       return "external pin";
    case ESP_RST_SW:        return "software";
    case ESP_RST_PANIC:     return "panic";
    case ESP_RST_INT_WDT:   return "interrupt watchdog";
    case ESP_RST_TASK_WDT:  return "task watchdog";
    case ESP_RST_WDT:       return "other watchdog";
    case ESP_RST_DEEPSLEEP: return "deep sleep";
    case ESP_RST_BROWNOUT:  return "brownout";
    case ESP_RST_USB:       return "USB";
    default:                return "other";
    }
}

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
    ESP_LOGI(kTag, "reset reason: %s", reset_reason_name(esp_reset_reason()));
}

}  // namespace

extern "C" void app_main()
{
    log_banner();

    for (;;) {
        const int64_t uptime_s = esp_timer_get_time() / 1'000'000;
        ESP_LOGI(kTag, "alive, uptime %" PRId64 " s, free heap %" PRIu32 " bytes",
                 uptime_s, esp_get_free_heap_size());
        vTaskDelay(kHeartbeatPeriod);
    }
}
