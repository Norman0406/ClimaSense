#include "sensors/sensor_task.h"

#include <algorithm>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <mutex>

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
#include "sensors/gas_index.h"
#include "sensors/scd41.h"
#include "sensors/sgp41.h"
#include "sensors/sht45.h"
#include "sensors/single_shot.h"
#include "sensors/snapshot.h"

namespace sensors {

namespace {

constexpr const char *kTag = "sensors";
constexpr TickType_t kTick = pdMS_TO_TICKS(1000);
constexpr uint32_t kStackBytes = 6144;  // four drivers, two gas index states, log formatting
// Above the app task (priority 1), well below ESP-IDF's Wi-Fi and network tasks.
constexpr UBaseType_t kPriority = 5;
// The handover to the app task: the only state shared with it.
std::mutex g_snapshot_lock;
SnapshotBuilder g_snapshot;

uint32_t uptime_s() { return static_cast<uint32_t>(esp_timer_get_time() / 1'000'000); }

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

void init_scd41(Scd41 &scd)
{
    // In case the SCD41 kept running periodic measurements across an ESP32 reset.
    if (auto r = scd.stop_periodic_measurement(); !r) {
        ESP_LOGW(kTag, "SCD41: stop command failed: %s", to_string(r.error()));
        return;
    }
    wait_ms(Scd41::kStopMs);
    if (const auto serial = scd.read_serial()) {
        ESP_LOGI(kTag, "SCD41: serial number 0x%012llx", static_cast<unsigned long long>(*serial));
    } else {
        ESP_LOGW(kTag, "SCD41: serial number read failed: %s", to_string(serial.error()));
    }
    if (const auto asc = scd.automatic_self_calibration_enabled()) {
        if (*asc) {
            ESP_LOGI(kTag, "SCD41: automatic self-calibration on");
        } else {
            ESP_LOGW(kTag, "SCD41: automatic self-calibration is OFF (factory default is on)");
        }
    }
}

// One tick of the SCD41's single-shot cycle. Runs at the end of the tick, after the BMP580;
// the schedule's first poll comes 6 ticks after the start, which covers the 5 s measurement
// even though the start is late in its tick. `pressure_milli_pa` is 0 if there is no BMP580
// reading yet.
void step_scd41(Scd41 &scd, SingleShotSchedule &schedule, Health &health, uint32_t tick,
                int32_t pressure_milli_pa)
{
    switch (schedule.next(tick)) {
    case SingleShotSchedule::Step::Wait:
        return;
    case SingleShotSchedule::Step::Start:
        if (pressure_milli_pa > 0) {
            if (auto r = scd.set_ambient_pressure(pressure_milli_pa); !r) {
                ESP_LOGW(kTag, "SCD41: pressure compensation not set: %s", to_string(r.error()));
            }
        }
        if (auto r = scd.start_single_shot(); r) {
            schedule.started(tick);
        } else {
            schedule.start_failed(tick);
            health.failed(r.error());
        }
        return;
    case SingleShotSchedule::Step::Poll: {
        const auto ready = scd.data_ready();
        if (ready && !*ready) {
            return;  // not yet; try again next tick
        }
        const auto reading = ready ? scd.read_measurement() : SensorResult<Scd41Reading>{std::unexpected(ready.error())};
        schedule.done();
        if (!reading) {
            health.failed(reading.error());
            return;
        }
        health.ok();
        {
            std::lock_guard<std::mutex> lock(g_snapshot_lock);
            g_snapshot.set_co2(reading->co2_ppm, uptime_s());
        }
        ESP_LOGI(kTag, "SCD41: %u ppm CO2 (own sensor %s C, %s %%RH)", reading->co2_ppm,
                 Milli(reading->temperature_mc).text, Milli(reading->humidity_mpercent).text);
        return;
    }
    case SingleShotSchedule::Step::GiveUp:
        schedule.done();
        health.failed(SensorError::NotReady);
        return;
    }
}

void init_sgp41(Sgp41 &sgp)
{
    if (auto r = sgp.request_serial(); !r) {
        ESP_LOGW(kTag, "SGP41: serial number request failed: %s", to_string(r.error()));
        return;
    }
    wait_ms(Sgp41::kSerialMs);
    if (const auto serial = sgp.read_serial()) {
        ESP_LOGI(kTag, "SGP41: serial number 0x%012llx", static_cast<unsigned long long>(*serial));
    } else {
        ESP_LOGW(kTag, "SGP41: serial number read failed: %s", to_string(serial.error()));
    }
}

// The SGP41's part of a tick: conditioning for its first 10 ticks, then one raw measurement,
// fed to both gas index algorithms. Must run every tick: the algorithms assume 1 s samples.
// `sht` is this tick's SHT45 reading, for compensation (defaults if it failed).
void step_sgp41(Sgp41 &sgp, GasIndex &voc, GasIndex &nox, Health &health, uint32_t &conditioning_left,
                const SensorResult<Sht45Reading> &sht, esp_log_level_t level)
{
    const uint16_t rh = sht ? Sgp41::humidity_ticks(sht->humidity_mpercent) : Sgp41::kDefaultHumidityTicks;
    const uint16_t t = sht ? Sgp41::temperature_ticks(sht->temperature_mc) : Sgp41::kDefaultTemperatureTicks;

    if (conditioning_left > 0) {
        --conditioning_left;
        if (auto r = sgp.start_conditioning(rh, t); !r) {
            health.failed(r.error());
            return;
        }
        wait_ms(Sgp41::kCommandMs);
        if (auto r = sgp.read_conditioning(); !r) {
            health.failed(r.error());
            return;
        }
        health.ok();
        if (conditioning_left == 0) {
            ESP_LOGI(kTag, "SGP41: conditioning done, measuring");
        }
        return;
    }

    if (auto r = sgp.start_measurement(rh, t); !r) {
        health.failed(r.error());
        return;
    }
    wait_ms(Sgp41::kCommandMs);
    const auto raw = sgp.read_measurement();
    if (!raw) {
        health.failed(raw.error());
        return;
    }
    health.ok();
    const int32_t voc_index = voc.process(raw->voc);
    const int32_t nox_index = nox.process(raw->nox);
    {
        std::lock_guard<std::mutex> lock(g_snapshot_lock);
        g_snapshot.set_gas_index(voc_index, nox_index);
    }
    if (voc_index == 0) {
        ESP_LOG_LEVEL_LOCAL(level, kTag, "SGP41: raw VOC %u, NOx %u (index algorithms still starting)",
                            raw->voc, raw->nox);
    } else {
        ESP_LOG_LEVEL_LOCAL(level, kTag, "SGP41: VOC index %" PRId32 ", NOx index %" PRId32 " (raw %u, %u)",
                            voc_index, nox_index, raw->voc, raw->nox);
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

    Sht45 sht45{bus};
    Health sht45_health{"SHT45"};
    init_sht45(sht45);

    Bmp580 bmp580{bus};
    Health bmp580_health{"BMP580"};
    bool bmp580_ready = init_bmp580(bmp580);
    int32_t last_pressure_milli_pa = 0;  // for the SCD41's pressure compensation

    Scd41 scd41{bus, wait_ms};
    Health scd41_health{"SCD41"};
    SingleShotSchedule scd41_schedule;
    init_scd41(scd41);

    Sgp41 sgp41{bus};
    Health sgp41_health{"SGP41"};
    GasIndex voc_index{GasIndex::Kind::Voc};
    GasIndex nox_index{GasIndex::Kind::Nox};
    uint32_t sgp41_conditioning_left = Sgp41::kConditioningSeconds;
    init_sgp41(sgp41);

    TickType_t last_wake = xTaskGetTickCount();
    for (uint32_t tick = 1;; ++tick) {
        vTaskDelayUntil(&last_wake, kTick);
        if (!bus.is_open()) {
            continue;
        }
        if (!bmp580_ready && tick % kRetryInitTicks == 0) {
            bmp580_ready = init_bmp580(bmp580);
        }

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
            {
                std::lock_guard<std::mutex> lock(g_snapshot_lock);
                g_snapshot.add_temperature_humidity(sht->temperature_mc, sht->humidity_mpercent);
            }
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
                last_pressure_milli_pa = bmp->pressure_milli_pa;
                {
                    std::lock_guard<std::mutex> lock(g_snapshot_lock);
                    g_snapshot.add_pressure(bmp->pressure_milli_pa);
                }
                ESP_LOG_LEVEL_LOCAL(level, kTag, "BMP580: %s hPa (die %s C)",
                                    Milli(bmp->pressure_milli_pa / 100).text, Milli(bmp->temperature_mc).text);
            } else {
                bmp580_health.failed(bmp.error());
            }
        }

        // After the SHT45, whose reading of this tick compensates it.
        step_sgp41(sgp41, voc_index, nox_index, sgp41_health, sgp41_conditioning_left, sht, level);

        // Last in the tick, so that even the first shot gets the pressure just read.
        step_scd41(scd41, scd41_schedule, scd41_health, tick, last_pressure_milli_pa);
    }
}

}  // namespace

SensorSnapshot take_snapshot()
{
    std::lock_guard<std::mutex> lock(g_snapshot_lock);
    return g_snapshot.take(uptime_s());
}

esp_err_t start_task()
{
    const BaseType_t ok = xTaskCreate(task, "sensors", kStackBytes, nullptr, kPriority, nullptr);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_ERR_NO_MEM, kTag, "task create");
    return ESP_OK;
}

}  // namespace sensors
