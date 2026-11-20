// KvStore on ESP-IDF's NVS, in its own namespace "settings". NVS must be initialised first
// (nvs_flash_init in app_main).
#pragma once

#include "esp_err.h"
#include "nvs.h"

#include "settings/kv_store.h"

namespace settings {

class NvsStore final : public KvStore {
public:
    static constexpr const char *kNamespace = "settings";

    NvsStore() = default;
    ~NvsStore() override;

    esp_err_t open();

    std::expected<std::size_t, KvError> get(const char *key, std::span<char> out) override;
    std::expected<void, KvError> set(const char *key, std::string_view value) override;
    std::expected<void, KvError> commit() override;

private:
    nvs_handle_t handle_ = 0;
    bool open_ = false;
};

}  // namespace settings
