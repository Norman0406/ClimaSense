// I2cBus on ESP-IDF's I2C master driver. Works on the normal controller (I2C_NUM_0) and the
// low-power one (LP_I2C_NUM_0, on the ESP32-C6 only on IO6/IO7).
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "driver/i2c_master.h"

#include "sensors/i2c_bus.h"

namespace sensors {

class EspI2cBus final : public I2cBus {
public:
    struct Config {
        i2c_port_num_t port;
        gpio_num_t sda;
        gpio_num_t scl;
        uint32_t frequency_hz;
    };

    EspI2cBus() = default;
    ~EspI2cBus() override { close(); }

    // Creates the bus. External pull-ups are assumed; the internal ones stay off.
    esp_err_t open(const Config &config);

    // Removes all devices and deletes the bus, which frees the pins. Must happen before the
    // bus's supply rail is switched off.
    void close();

    bool is_open() const { return bus_ != nullptr; }

    I2cResult probe(uint8_t address) override;
    I2cResult write(uint8_t address, std::span<const uint8_t> data) override;
    I2cResult read(uint8_t address, std::span<uint8_t> data) override;
    I2cResult write_read(uint8_t address, std::span<const uint8_t> tx, std::span<uint8_t> rx) override;

private:
    static constexpr std::size_t kMaxDevices = 8;
    static constexpr int kTimeoutMs = 50;

    struct Device {
        uint8_t address;
        i2c_master_dev_handle_t handle;
    };

    // The driver needs a handle per device address; they are added on first use.
    i2c_master_dev_handle_t device(uint8_t address);

    i2c_master_bus_handle_t bus_ = nullptr;
    uint32_t frequency_hz_ = 0;
    std::array<Device, kMaxDevices> devices_{};
    std::size_t device_count_ = 0;
};

}  // namespace sensors
