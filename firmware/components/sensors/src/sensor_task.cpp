#include "sensors/sensor_task.h"

#include <algorithm>
#include <cinttypes>
#include <cstdint>
#include <cstdio>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board/pins.h"
#include "sensors/bmp580.h"
#include "sensors/bus_scan.h"
#include "sensors/devices.h"
#include "sensors/esp_i2c_bus.h"
#include "sensors/sht45.h"

namespace sensors {

namespace {

constexpr const char *kTag = "sensors";
constexpr TickType_t kTick = pdMS_TO_TICKS(1000);
constexpr uint32_t kStackBytes = 4096;
// Above the app task (priority 1), well below ESP-IDF's Wi-Fi and network tasks.
constexpr UBaseType_t kPriority = 5;
// Readings are logged at INFO every this many ticks (every tick at DEBUG).
constexpr uint32_t kLogEveryTicks = 10;
// A sensor whose start-up failed is tried again every this many ticks.
constexpr uint32_t kRetryInitTicks = 10;

// Waits at least `ms` (a plain vTaskDelay can return up to one tick early).
void wait_ms(uint32_t ms) { vTaskDelay(pdMS_TO_TICKS(ms) + 1); }

// Milli-units as text with two decimals, e.g. -1234 -> "-1.23".
struct Milli {
    char text[16];
    explicit Milli(int32_t value)
    {
        const int32_t abs = value < 0 ? -value : value;
        snprintf(text, sizeof(text), "%s%" PRId32 ".%02" PRId32, value < 0 ? "-" : "",
                 abs / 1000, (abs % 1000) / 10);
    }
};

// One sensor's error state, so that errors are logged when they start and end, not every second.
class Health {
public:
    explicit Health(const char *name) : name_(name) {}

    void ok()
    {
        if (failures_ > 0) {
            ESP_LOGI(kTag, "%s: working again after %" PRIu32 " failed readings", name_, failures_);
        }
        failures_ = 0;
    }

    void failed(SensorError error)
    {
        if (failures_ == 0) {
            ESP_LOGW(kTag, "%s: %s", name_, to_string(error));
        }
        ++failures_;
    }

private:
    const char *name_;
    uint32_t failures_ = 0;
};

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

void init_sht45(Sht45 &sht)
{
    if (auto r = sht.soft_reset(); !r) {
        ESP_LOGW(kTag, "SHT45: reset failed: %s", to_string(r.error()));
        return;
    }
    wait_ms(Sht45::kResetMs);
    if (auto r = sht.request_serial(); !r) {
        ESP_LOGW(kTag, "SHT45: serial number request failed: %s", to_string(r.error()));
        return;
    }
    wait_ms(Sht45::kSerialMs);
    if (const auto serial = sht.read_serial()) {
        ESP_LOGI(kTag, "SHT45: serial number 0x%08" PRIx32, *serial);
    } else {
        ESP_LOGW(kTag, "SHT45: serial number read failed: %s", to_string(serial.error()));
    }
}

bool init_bmp580(Bmp580 &bmp)
{
    if (auto r = bmp.soft_reset(); !r) {
        ESP_LOGW(kTag, "BMP580: reset failed: %s", to_string(r.error()));
        return false;
    }
    wait_ms(Bmp580::kResetMs);
    const auto chip_id = bmp.check_after_reset();
    if (!chip_id) {
        ESP_LOGW(kTag, "BMP580: start-up check failed: %s", to_string(chip_id.error()));
        return false;
    }
    if (auto r = bmp.configure(); !r) {
        ESP_LOGW(kTag, "BMP580: configuration failed: %s", to_string(r.error()));
        return false;
    }
    ESP_LOGI(kTag, "BMP580: chip ID 0x%02x, configured", *chip_id);
    return true;
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

    Sht45 sht45{bus};
    Health sht45_health{"SHT45"};
    init_sht45(sht45);

    Bmp580 bmp580{bus};
    Health bmp580_health{"BMP580"};
    bool bmp580_ready = init_bmp580(bmp580);

    TickType_t last_wake = xTaskGetTickCount();
    for (uint32_t tick = 1;; ++tick) {
        vTaskDelayUntil(&last_wake, kTick);
        if (!bus.is_open()) {
            continue;
        }
        if (!bmp580_ready && tick % kRetryInitTicks == 0) {
            bmp580_ready = init_bmp580(bmp580);
        }
        // Still to come in step 4: SGP41 every tick, SCD41 single shot every 5 minutes.

        // Start both measurements, wait once for the slower one, then read both.
        const SensorResult<void> sht45_started = sht45.start_measurement();
        const SensorResult<void> bmp580_started =
            bmp580_ready ? bmp580.start_measurement() : SensorResult<void>{std::unexpected(SensorError::NotReady)};
        wait_ms(std::max(Sht45::kMeasureMs, Bmp580::kMeasureMs));

        const bool info = tick % kLogEveryTicks == 0;
        const esp_log_level_t level = info ? ESP_LOG_INFO : ESP_LOG_DEBUG;

        const SensorResult<Sht45Reading> sht = sht45_started
            ? sht45.read_measurement() : SensorResult<Sht45Reading>{std::unexpected(sht45_started.error())};
        if (sht) {
            sht45_health.ok();
            ESP_LOG_LEVEL_LOCAL(level, kTag, "SHT45: %s C, %s %%RH",
                                Milli(sht->temperature_mc).text, Milli(sht->humidity_mpercent).text);
        } else {
            sht45_health.failed(sht.error());
        }

        if (bmp580_ready) {
            const SensorResult<Bmp580Reading> bmp = bmp580_started
                ? bmp580.read_measurement() : SensorResult<Bmp580Reading>{std::unexpected(bmp580_started.error())};
            if (bmp) {
                bmp580_health.ok();
                ESP_LOG_LEVEL_LOCAL(level, kTag, "BMP580: %s hPa (die %s C)",
                                    Milli(bmp->pressure_milli_pa / 100).text, Milli(bmp->temperature_mc).text);
            } else {
                bmp580_health.failed(bmp.error());
            }
        }
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
