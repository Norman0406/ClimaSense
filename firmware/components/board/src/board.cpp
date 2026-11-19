#include "board/board.h"

#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"

#include "board/pins.h"

namespace board {

namespace {

constexpr const char *kTag = "board";

bool g_sensor_rail_on = true;
bool g_qwiic_rail_on = false;

constexpr uint64_t bit(gpio_num_t pin) { return 1ULL << pin; }

// Output with a defined level from the first moment: the level is latched before the
// output driver is enabled, so the pin never glitches to the other state.
esp_err_t config_output(gpio_num_t pin, bool level)
{
    ESP_RETURN_ON_ERROR(gpio_set_level(pin, level ? 1 : 0), kTag, "set level IO%d", pin);
    gpio_config_t cfg{};
    cfg.pin_bit_mask = bit(pin);
    cfg.mode = GPIO_MODE_OUTPUT;
    cfg.pull_up_en = GPIO_PULLUP_DISABLE;
    cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    cfg.intr_type = GPIO_INTR_DISABLE;
    return gpio_config(&cfg);
}

// Plain inputs without internal pulls: neither drives nor feeds anything.
esp_err_t release_pins(gpio_num_t sda, gpio_num_t scl)
{
    gpio_config_t cfg{};
    cfg.pin_bit_mask = bit(sda) | bit(scl);
    cfg.mode = GPIO_MODE_INPUT;
    cfg.pull_up_en = GPIO_PULLUP_DISABLE;
    cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    cfg.intr_type = GPIO_INTR_DISABLE;
    return gpio_config(&cfg);
}

}  // namespace

esp_err_t init()
{
    ESP_RETURN_ON_ERROR(config_output(pins::kSensEn, true), kTag, "SENS_EN");
    ESP_RETURN_ON_ERROR(config_output(pins::kQwiicEn, false), kTag, "QWIIC_EN");
    g_sensor_rail_on = true;
    g_qwiic_rail_on = false;

    gpio_config_t intr{};
    intr.pin_bit_mask = bit(pins::kBmpInt);
    intr.mode = GPIO_MODE_INPUT;
    intr.pull_up_en = GPIO_PULLUP_DISABLE;
    intr.pull_down_en = GPIO_PULLDOWN_ENABLE;
    intr.intr_type = GPIO_INTR_DISABLE;
    ESP_RETURN_ON_ERROR(gpio_config(&intr), kTag, "BMP_INT");

    ESP_LOGI(kTag, "sensor rail on, Qwiic rail off");
    return ESP_OK;
}

esp_err_t set_sensor_rail(bool on)
{
    if (!on) {
        ESP_RETURN_ON_ERROR(release_pins(pins::kI2cSensSda, pins::kI2cSensScl), kTag, "release sensor bus");
    }
    ESP_RETURN_ON_ERROR(gpio_set_level(pins::kSensEn, on ? 1 : 0), kTag, "SENS_EN");
    g_sensor_rail_on = on;
    ESP_LOGI(kTag, "sensor rail %s", on ? "on" : "off");
    return ESP_OK;
}

bool sensor_rail_on() { return g_sensor_rail_on; }

esp_err_t set_qwiic_rail(bool on)
{
    if (!on) {
        ESP_RETURN_ON_ERROR(release_pins(pins::kI2cQwiicSda, pins::kI2cQwiicScl), kTag, "release Qwiic bus");
    }
    ESP_RETURN_ON_ERROR(gpio_set_level(pins::kQwiicEn, on ? 1 : 0), kTag, "QWIIC_EN");
    g_qwiic_rail_on = on;
    ESP_LOGI(kTag, "Qwiic rail %s", on ? "on" : "off");
    return ESP_OK;
}

bool qwiic_rail_on() { return g_qwiic_rail_on; }

}  // namespace board
