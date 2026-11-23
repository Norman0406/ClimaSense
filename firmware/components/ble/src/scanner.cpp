#include "ble/scanner.h"

#include <atomic>
#include <mutex>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "ble/fhn_frame.h"

// NimBLE's headers last: they are C and define macros (min, max) that break C++ headers.
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#undef min
#undef max

namespace ble {

namespace {

constexpr const char *kTag = "ble";

std::mutex g_table_lock;
SightingTable g_table;  // under g_table_lock
std::atomic<bool> g_new_tag{false};

std::mutex g_scan_lock;  // serialises starting and stopping the scan
bool g_started = false;
std::atomic<bool> g_synced{false};  // the host and the controller are ready
std::atomic<bool> g_wanted{false};

uint32_t uptime_s() { return static_cast<uint32_t>(esp_timer_get_time() / 1'000'000); }

// Called in the NimBLE host task for every advertisement the controller received.
int on_gap_event(struct ble_gap_event *event, void *)
{
    if (event->type != BLE_GAP_EVENT_DISC) {
        return 0;
    }
    const auto frame = parse_fhn({event->disc.data, event->disc.length_data});
    if (!frame) {
        return 0;
    }
    const std::lock_guard<std::mutex> lock(g_table_lock);
    if (g_table.add(*frame, event->disc.rssi, uptime_s())) {
        g_new_tag = true;
    }
    return 0;
}

// Brings the controller's scan in line with what is wanted.
void apply()
{
    const std::lock_guard<std::mutex> lock(g_scan_lock);
    if (!g_synced) {
        return;
    }
    const bool active = ble_gap_disc_active() != 0;
    if (g_wanted && !active) {
        struct ble_gap_disc_params params {};
        params.itvl = static_cast<uint16_t>(kScanIntervalMs * 1000 / 625);  // units of 0.625 ms
        params.window = static_cast<uint16_t>(kScanWindowMs * 1000 / 625);
        params.passive = 1;  // listen only: no scan requests are sent
        // No duplicate filter: it works by address, and every frame counts as a sign of life.
        params.filter_duplicates = 0;
        // The own address type only matters for active scanning.
        const int rc = ble_gap_disc(BLE_OWN_ADDR_PUBLIC, BLE_HS_FOREVER, &params, on_gap_event, nullptr);
        if (rc != 0) {
            ESP_LOGE(kTag, "scan not started: NimBLE error %d", rc);
        } else {
            ESP_LOGI(kTag, "scanning for tag frames, %u ms of every %u ms", static_cast<unsigned>(kScanWindowMs),
                     static_cast<unsigned>(kScanIntervalMs));
        }
    } else if (!g_wanted && active) {
        const int rc = ble_gap_disc_cancel();
        if (rc != 0) {
            ESP_LOGE(kTag, "scan not stopped: NimBLE error %d", rc);
        } else {
            ESP_LOGI(kTag, "scan paused");
        }
    }
}

void on_sync()
{
    if (const int rc = ble_hs_util_ensure_addr(0); rc != 0) {
        ESP_LOGE(kTag, "no Bluetooth address: NimBLE error %d", rc);
        return;
    }
    g_synced = true;
    apply();
}

// The controller reset itself; the host syncs again and on_sync restarts the scan.
void on_reset(int reason)
{
    g_synced = false;
    ESP_LOGW(kTag, "Bluetooth controller reset, reason %d", reason);
}

void host_task(void *)
{
    nimble_port_run();  // returns only if the host is stopped
    nimble_port_freertos_deinit();
}

}  // namespace

esp_err_t start()
{
    ESP_RETURN_ON_FALSE(!g_started, ESP_ERR_INVALID_STATE, kTag, "already started");
    ESP_RETURN_ON_ERROR(nimble_port_init(), kTag, "Bluetooth controller and host");
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    nimble_port_freertos_init(host_task);
    g_started = true;
    return ESP_OK;
}

void set_scanning(bool wanted)
{
    if (!g_started || g_wanted.exchange(wanted) == wanted) {
        return;
    }
    apply();
}

bool scanning() { return g_started && g_synced && ble_gap_disc_active() != 0; }

bool take_new_tag() { return g_new_tag.exchange(false); }

void take_report(uint32_t now_s, Report &report)
{
    const std::lock_guard<std::mutex> lock(g_table_lock);
    g_table.take_report(now_s, report);
}

}  // namespace ble
