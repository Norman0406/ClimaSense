#include "board/led.h"

#include <initializer_list>

#include "driver/ledc.h"
#include "esp_check.h"

#include "board/pins.h"

namespace board::led {

namespace {

constexpr const char *kTag = "led";

constexpr ledc_mode_t kMode = LEDC_LOW_SPEED_MODE;
constexpr ledc_timer_t kTimer = LEDC_TIMER_0;
constexpr uint32_t kFrequencyHz = 4000;
static_assert(kDutyMax == (1u << 10) - 1, "LEDC resolution must match kDutyMax");

struct Channel {
    gpio_num_t pin;
    ledc_channel_t channel;
};

// Order on the board is G, R, B on IO21..IO23.
constexpr Channel kRed{pins::kLedR, LEDC_CHANNEL_0};
constexpr Channel kGreen{pins::kLedG, LEDC_CHANNEL_1};
constexpr Channel kBlue{pins::kLedB, LEDC_CHANNEL_2};

esp_err_t config_channel(const Channel &ch)
{
    ledc_channel_config_t cfg{};
    cfg.gpio_num = ch.pin;
    cfg.speed_mode = kMode;
    cfg.channel = ch.channel;
    cfg.timer_sel = kTimer;
    cfg.duty = 0;
    cfg.hpoint = 0;
    // The LED is active low: inverting the output makes duty 0 = pin high = off.
    cfg.flags.output_invert = 1;
    return ledc_channel_config(&cfg);
}

esp_err_t set_channel(const Channel &ch, uint32_t duty)
{
    ESP_RETURN_ON_ERROR(ledc_set_duty(kMode, ch.channel, duty), kTag, "set duty");
    return ledc_update_duty(kMode, ch.channel);
}

}  // namespace

esp_err_t init()
{
    ledc_timer_config_t timer{};
    timer.speed_mode = kMode;
    timer.duty_resolution = LEDC_TIMER_10_BIT;
    timer.timer_num = kTimer;
    timer.freq_hz = kFrequencyHz;
    timer.clk_cfg = LEDC_AUTO_CLK;
    ESP_RETURN_ON_ERROR(ledc_timer_config(&timer), kTag, "timer");

    for (const Channel &ch : {kRed, kGreen, kBlue}) {
        ESP_RETURN_ON_ERROR(config_channel(ch), kTag, "channel IO%d", ch.pin);
    }
    return ESP_OK;
}

esp_err_t set(Rgb colour, uint8_t brightness)
{
    const Duty duty = to_duty(colour, brightness);
    ESP_RETURN_ON_ERROR(set_channel(kRed, duty.r), kTag, "red");
    ESP_RETURN_ON_ERROR(set_channel(kGreen, duty.g), kTag, "green");
    return set_channel(kBlue, duty.b);
}

}  // namespace board::led
