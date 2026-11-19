#include "sensors/sensor_task.h"

#include <cinttypes>
#include <cstdint>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board/pins.h"
#include "sensors/bus_scan.h"
#include "sensors/devices.h"
#include "sensors/esp_i2c_bus.h"

namespace sensors {

namespace {

constexpr const char *kTag = "sensors";
constexpr TickType_t kTick = pdMS_TO_TICKS(1000);
constexpr uint32_t kStackBytes = 4096;
// Above the app task (priority 1), well below ESP-IDF's Wi-Fi and network tasks.
constexpr UBaseType_t kPriority = 5;

void log_scan(const ScanResult &result)
{
    const ScanReport report = compare(result, kSensorBusDevices);

    for (const DeviceInfo &d : kSensorBusDevices) {
        if (result.found(d.address)) {
            ESP_LOGI(kTag, "%-6s at 0x%02x: found", d.name, d.address);
        } else if (report.missing.test(d.address) && !result.fault) {
            ESP_LOGE(kTag, "%-6s at 0x%02x: MISSING", d.name, d.address);
        }
    }
    for (unsigned a = 0; a < 128; ++a) {
        if (report.unexpected.test(a)) {
            ESP_LOGW(kTag, "unexpected device at 0x%02x", a);
        }
    }
    if (result.fault) {
        ESP_LOGE(kTag, "bus fault (%s) while probing 0x%02x, scan stopped; SDA/SCL held low, "
                 "or the sensor rail is off", to_string(result.fault->error), result.fault->address);
    } else if (report.all_as_expected(result)) {
        ESP_LOGI(kTag, "sensor bus: all %u devices found", static_cast<unsigned>(kSensorBusDevices.size()));
    }
}

void wait_for_power_up()
{
    // The sensor rail is on from power-up (pull-up on SENS_EN), so the time since boot counts.
    const int64_t ready_us = static_cast<int64_t>(kPowerUpMs) * 1000;
    const int64_t now_us = esp_timer_get_time();
    if (now_us < ready_us) {
        vTaskDelay(pdMS_TO_TICKS((ready_us - now_us) / 1000) + 1);
    }
}

void task(void *)
{
    wait_for_power_up();

    EspI2cBus bus;
    const esp_err_t err = bus.open({
        .port = LP_I2C_NUM_0,
        .sda = board::pins::kI2cSensSda,
        .scl = board::pins::kI2cSensScl,
        .frequency_hz = kSensorBusHz,
    });
    if (err != ESP_OK) {
        ESP_LOGE(kTag, "cannot open the sensor bus: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(kTag, "sensor bus open (LP I2C, IO%d/IO%d, %" PRIu32 " kHz)",
                 board::pins::kI2cSensSda, board::pins::kI2cSensScl, kSensorBusHz / 1000);
        log_scan(scan_bus(bus));
    }

    TickType_t last_wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&last_wake, kTick);
        // Step 4: read SHT45, BMP580, SGP41 every tick; SCD41 single shot every 5 minutes.
    }
}

}  // namespace

esp_err_t start_task()
{
    const BaseType_t ok = xTaskCreate(task, "sensors", kStackBytes, nullptr, kPriority, nullptr);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_ERR_NO_MEM, kTag, "task create");
    return ESP_OK;
}

}  // namespace sensors
