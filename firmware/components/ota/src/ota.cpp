#include "ota/ota.h"

#include <algorithm>
#include <atomic>

#include "esp_app_desc.h"
#include "esp_check.h"
#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace ota {

namespace {

constexpr const char *kTag = "ota";

std::atomic<bool> g_busy{false};
UpdateCommand g_command;
StatusFn g_status = nullptr;

void report(std::string_view state, std::optional<int> progress = std::nullopt, std::string_view detail = {})
{
    if (g_status != nullptr) {
        g_status(status_json(state, progress, detail));
    }
}

const char *running_version() { return esp_app_get_description()->version; }

std::string describe(esp_err_t err)
{
    if (err == ESP_ERR_OTA_VALIDATE_FAILED) {
        return "image check failed (not signed with our key, or damaged)";
    }
    return esp_err_to_name(err);
}

void restart_soon()
{
    vTaskDelay(pdMS_TO_TICKS(2000));  // lets the last status message and the page reach their way
    esp_restart();
}

void update_task(void *)
{
    ESP_LOGW(kTag, "update from %s%s", g_command.url.c_str(), g_command.force ? " (forced)" : "");
    report("starting", std::nullopt, g_command.url);

    esp_http_client_config_t http{};
    http.url = g_command.url.c_str();
    http.timeout_ms = 15000;
    http.keep_alive_enable = true;
    esp_https_ota_config_t config{};
    config.http_config = &http;

    esp_https_ota_handle_t handle = nullptr;
    esp_err_t err = esp_https_ota_begin(&config, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(kTag, "update not started: %s", describe(err).c_str());
        report("failed", std::nullopt, "download: " + describe(err));
        g_busy = false;
        vTaskDelete(nullptr);
        return;
    }

    esp_app_desc_t desc{};
    if (esp_https_ota_get_img_desc(handle, &desc) != ESP_OK) {
        esp_https_ota_abort(handle);
        report("failed", std::nullopt, "not a firmware image");
        g_busy = false;
        vTaskDelete(nullptr);
        return;
    }
    const VersionCheck check = check_version(running_version(), desc.version);
    if (!allowed(check, g_command.force)) {
        esp_https_ota_abort(handle);
        const std::string why = std::string("version ") + desc.version + " is " +
                                (check == VersionCheck::Older ? "older than " : "not comparable with ") +
                                running_version() + "; add \"force\" to install it anyway";
        ESP_LOGW(kTag, "update refused: %s", why.c_str());
        report("refused", std::nullopt, why);
        g_busy = false;
        vTaskDelete(nullptr);
        return;
    }
    report("downloading", 0, desc.version);

    int last_reported = 0;
    do {
        err = esp_https_ota_perform(handle);
        const int size = esp_https_ota_get_image_size(handle);
        const int read = esp_https_ota_get_image_len_read(handle);
        if (size > 0) {
            const int percent = static_cast<int>(static_cast<int64_t>(read) * 100 / size);
            if (percent >= last_reported + 10) {
                last_reported = percent - percent % 10;
                report("downloading", last_reported);
            }
        }
    } while (err == ESP_ERR_HTTPS_OTA_IN_PROGRESS);

    if (err == ESP_OK && !esp_https_ota_is_complete_data_received(handle)) {
        err = ESP_ERR_INVALID_SIZE;
    }
    if (err != ESP_OK) {
        esp_https_ota_abort(handle);
        ESP_LOGE(kTag, "download failed: %s", describe(err).c_str());
        report("failed", std::nullopt, "download: " + describe(err));
        g_busy = false;
        vTaskDelete(nullptr);
        return;
    }
    err = esp_https_ota_finish(handle);  // checks the image, including its signature
    if (err != ESP_OK) {
        ESP_LOGE(kTag, "image not installed: %s", describe(err).c_str());
        report("failed", std::nullopt, describe(err));
        g_busy = false;
        vTaskDelete(nullptr);
        return;
    }
    ESP_LOGW(kTag, "version %s installed; restarting to try it", desc.version);
    report("restarting", 100, desc.version);
    restart_soon();
}

}  // namespace

esp_err_t start_from_url(const UpdateCommand &command, StatusFn status)
{
    if (on_trial()) {
        if (status != nullptr) {
            status(status_json("refused", std::nullopt, "the running firmware is still on trial"));
        }
        return ESP_ERR_INVALID_STATE;
    }
    if (g_busy.exchange(true)) {
        if (status != nullptr) {
            status(status_json("refused", std::nullopt, "an update is already running"));
        }
        return ESP_ERR_INVALID_STATE;
    }
    g_command = command;
    g_status = status;
    if (xTaskCreate(update_task, "ota", 8192, nullptr, 3, nullptr) != pdPASS) {
        g_busy = false;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

bool busy() { return g_busy; }

// --- Upload ------------------------------------------------------------------------------------

esp_err_t Upload::fail(esp_err_t err, std::string why)
{
    error_ = std::move(why);
    abort();
    return err;
}

esp_err_t Upload::begin(bool force)
{
    if (on_trial()) {
        error_ = "the running firmware is still on trial; try again in a few minutes";
        return ESP_ERR_INVALID_STATE;
    }
    if (g_busy.exchange(true)) {
        error_ = "an update is already running";
        return ESP_ERR_INVALID_STATE;
    }
    const esp_partition_t *partition = esp_ota_get_next_update_partition(nullptr);
    if (partition == nullptr) {
        g_busy = false;
        error_ = "no update slot";
        return ESP_ERR_NOT_FOUND;
    }
    esp_ota_handle_t handle = 0;
    if (const esp_err_t err = esp_ota_begin(partition, OTA_WITH_SEQUENTIAL_WRITES, &handle); err != ESP_OK) {
        g_busy = false;
        error_ = esp_err_to_name(err);
        return err;
    }
    handle_ = handle;
    partition_ = partition;
    open_ = true;
    force_ = force;
    version_checked_ = false;
    head_length_ = 0;
    error_.clear();
    version_.clear();
    ESP_LOGW(kTag, "upload started%s", force ? " (older versions allowed)" : "");
    return ESP_OK;
}

esp_err_t Upload::write(std::span<const uint8_t> data)
{
    if (!open_) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!version_checked_) {
        // Collect the start of the image, check its version, then write what was collected.
        const std::size_t take = std::min(data.size(), head_.size() - head_length_);
        std::copy_n(data.begin(), take, head_.begin() + static_cast<std::ptrdiff_t>(head_length_));
        head_length_ += take;
        data = data.subspan(take);
        if (head_length_ < head_.size()) {
            return ESP_OK;
        }
        const auto version = image_version(head_);
        if (!version) {
            return fail(ESP_ERR_INVALID_ARG, "this is not a ClimaSense firmware image (.bin)");
        }
        const VersionCheck check = check_version(running_version(), *version);
        if (!allowed(check, force_)) {
            return fail(ESP_ERR_INVALID_VERSION,
                        "version " + *version + " is older than " + running_version() +
                            " (or not comparable); tick \"allow an older version\" to install it anyway");
        }
        version_ = *version;
        version_checked_ = true;
        if (const esp_err_t err = esp_ota_write(handle_, head_.data(), head_.size()); err != ESP_OK) {
            return fail(err, std::string("writing failed: ") + esp_err_to_name(err));
        }
    }
    if (!data.empty()) {
        if (const esp_err_t err = esp_ota_write(handle_, data.data(), data.size()); err != ESP_OK) {
            return fail(err, std::string("writing failed: ") + esp_err_to_name(err));
        }
    }
    return ESP_OK;
}

esp_err_t Upload::finish()
{
    if (!open_ || !version_checked_) {
        return fail(ESP_ERR_INVALID_SIZE, "the upload ended too early");
    }
    open_ = false;
    if (const esp_err_t err = esp_ota_end(handle_); err != ESP_OK) {  // checks image and signature
        g_busy = false;
        error_ = describe(err);
        return err;
    }
    const auto *partition = static_cast<const esp_partition_t *>(partition_);
    if (const esp_err_t err = esp_ota_set_boot_partition(partition); err != ESP_OK) {
        g_busy = false;
        error_ = esp_err_to_name(err);
        return err;
    }
    ESP_LOGW(kTag, "version %s uploaded and installed", version_.c_str());
    return ESP_OK;  // stays busy: the caller restarts
}

void Upload::abort()
{
    if (open_) {
        esp_ota_abort(handle_);
        open_ = false;
    }
    g_busy = false;
}

// --- Trial ---------------------------------------------------------------------------------------

bool on_trial()
{
    esp_ota_img_states_t state{};
    const esp_partition_t *running = esp_ota_get_running_partition();
    return running != nullptr && esp_ota_get_state_partition(running, &state) == ESP_OK &&
           state == ESP_OTA_IMG_PENDING_VERIFY;
}

void accept()
{
    if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK) {
        ESP_LOGI(kTag, "firmware %s confirmed after its trial", running_version());
    }
}

void reject()
{
    ESP_LOGE(kTag, "firmware %s failed its trial; returning to the previous one", running_version());
    vTaskDelay(pdMS_TO_TICKS(500));  // the log line into the ring, for the next boot report
    esp_ota_mark_app_invalid_rollback_and_reboot();
}

}  // namespace ota
