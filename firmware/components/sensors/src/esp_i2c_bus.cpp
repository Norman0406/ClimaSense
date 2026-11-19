#include "sensors/esp_i2c_bus.h"

#include "esp_check.h"
#include "esp_log.h"

namespace sensors {

namespace {

constexpr const char *kTag = "i2c";

I2cResult to_result(esp_err_t err)
{
    switch (err) {
    case ESP_OK:                   return {};
    case ESP_ERR_NOT_FOUND:        // probe: no ACK
    case ESP_ERR_INVALID_RESPONSE: // transfers: NACK
        return std::unexpected(I2cError::Nack);
    case ESP_ERR_TIMEOUT:          return std::unexpected(I2cError::Timeout);
    default:                       return std::unexpected(I2cError::Other);
    }
}

}  // namespace

esp_err_t EspI2cBus::open(const Config &config)
{
    ESP_RETURN_ON_FALSE(bus_ == nullptr, ESP_ERR_INVALID_STATE, kTag, "already open");

    i2c_master_bus_config_t cfg{};
    cfg.i2c_port = config.port;
    cfg.sda_io_num = config.sda;
    cfg.scl_io_num = config.scl;
#if SOC_LP_I2C_SUPPORTED
    if (config.port >= SOC_HP_I2C_NUM) {
        cfg.lp_source_clk = LP_I2C_SCLK_DEFAULT;
    } else {
        cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    }
#else
    cfg.clk_source = I2C_CLK_SRC_DEFAULT;
#endif
    cfg.glitch_ignore_cnt = 7;
    cfg.flags.enable_internal_pullup = 0;  // 4.7 kOhm on the board

    ESP_RETURN_ON_ERROR(i2c_new_master_bus(&cfg, &bus_), kTag, "new bus on port %d", config.port);
    frequency_hz_ = config.frequency_hz;
    device_count_ = 0;
    return ESP_OK;
}

void EspI2cBus::close()
{
    if (bus_ == nullptr) {
        return;
    }
    for (std::size_t i = 0; i < device_count_; ++i) {
        i2c_master_bus_rm_device(devices_[i].handle);
    }
    device_count_ = 0;
    i2c_del_master_bus(bus_);
    bus_ = nullptr;
}

i2c_master_dev_handle_t EspI2cBus::device(uint8_t address)
{
    for (std::size_t i = 0; i < device_count_; ++i) {
        if (devices_[i].address == address) {
            return devices_[i].handle;
        }
    }
    if (bus_ == nullptr || device_count_ == kMaxDevices) {
        return nullptr;
    }
    i2c_device_config_t cfg{};
    cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    cfg.device_address = address;
    cfg.scl_speed_hz = frequency_hz_;
    i2c_master_dev_handle_t handle = nullptr;
    if (i2c_master_bus_add_device(bus_, &cfg, &handle) != ESP_OK) {
        return nullptr;
    }
    devices_[device_count_++] = Device{address, handle};
    return handle;
}

I2cResult EspI2cBus::probe(uint8_t address)
{
    if (bus_ == nullptr) {
        return std::unexpected(I2cError::Other);
    }
    return to_result(i2c_master_probe(bus_, address, kTimeoutMs));
}

I2cResult EspI2cBus::write(uint8_t address, std::span<const uint8_t> data)
{
    i2c_master_dev_handle_t dev = device(address);
    if (dev == nullptr) {
        return std::unexpected(I2cError::Other);
    }
    return to_result(i2c_master_transmit(dev, data.data(), data.size(), kTimeoutMs));
}

I2cResult EspI2cBus::read(uint8_t address, std::span<uint8_t> data)
{
    i2c_master_dev_handle_t dev = device(address);
    if (dev == nullptr) {
        return std::unexpected(I2cError::Other);
    }
    return to_result(i2c_master_receive(dev, data.data(), data.size(), kTimeoutMs));
}

I2cResult EspI2cBus::write_read(uint8_t address, std::span<const uint8_t> tx, std::span<uint8_t> rx)
{
    i2c_master_dev_handle_t dev = device(address);
    if (dev == nullptr) {
        return std::unexpected(I2cError::Other);
    }
    return to_result(i2c_master_transmit_receive(dev, tx.data(), tx.size(), rx.data(), rx.size(), kTimeoutMs));
}

}  // namespace sensors
