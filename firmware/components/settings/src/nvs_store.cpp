#include "settings/nvs_store.h"

#include <algorithm>
#include <array>

namespace settings {

namespace {

// The longest value of any setting (the 64-character Wi-Fi password) plus its NUL.
constexpr std::size_t kMaxValue = 64 + 1;

}  // namespace

NvsStore::~NvsStore()
{
    if (open_) {
        nvs_close(handle_);
    }
}

esp_err_t NvsStore::open()
{
    if (open_) {
        return ESP_OK;
    }
    const esp_err_t err = nvs_open(kNamespace, NVS_READWRITE, &handle_);
    open_ = err == ESP_OK;
    return err;
}

std::expected<std::size_t, KvError> NvsStore::get(const char *key, std::span<char> out)
{
    if (!open_ || out.empty()) {
        return std::unexpected(KvError::Failed);
    }
    std::size_t length = out.size();  // in: buffer size, out: bytes including the NUL
    switch (nvs_get_str(handle_, key, out.data(), &length)) {
    case ESP_OK:
        return length > 0 ? length - 1 : 0;
    case ESP_ERR_NVS_NOT_FOUND:
        return std::unexpected(KvError::NotFound);
    case ESP_ERR_NVS_INVALID_LENGTH:
        return std::unexpected(KvError::TooLong);
    default:
        return std::unexpected(KvError::Failed);
    }
}

std::expected<void, KvError> NvsStore::set(const char *key, std::string_view value)
{
    if (!open_ || value.size() >= kMaxValue) {
        return std::unexpected(KvError::Failed);
    }
    std::array<char, kMaxValue> text{};  // NVS wants a NUL-terminated string
    std::copy(value.begin(), value.end(), text.begin());
    if (nvs_set_str(handle_, key, text.data()) != ESP_OK) {
        return std::unexpected(KvError::Failed);
    }
    return {};
}

std::expected<void, KvError> NvsStore::commit()
{
    if (!open_ || nvs_commit(handle_) != ESP_OK) {
        return std::unexpected(KvError::Failed);
    }
    return {};
}

}  // namespace settings
