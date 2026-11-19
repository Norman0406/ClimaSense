#include "board/button.h"

#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_timer.h"
#include "freertos/queue.h"

#include "board/pins.h"

namespace board::button {

namespace {

constexpr const char *kTag = "button";
constexpr uint64_t kPollPeriodUs = 10'000;
constexpr UBaseType_t kQueueLength = 4;

PressDetector g_detector;
QueueHandle_t g_events = nullptr;
esp_timer_handle_t g_timer = nullptr;

// Runs in the esp_timer task: keep it short, never block.
void poll(void *)
{
    const bool pressed = gpio_get_level(pins::kButton) == 0;  // low when pressed
    const auto now_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000);
    if (const auto event = g_detector.update(pressed, now_ms)) {
        // If the queue is full the app is not listening; dropping the event is fine.
        xQueueSend(g_events, &*event, 0);
    }
}

}  // namespace

esp_err_t init()
{
    // The board has a 10 kOhm pull-up; the internal one only matters if that is missing.
    gpio_config_t cfg{};
    cfg.pin_bit_mask = 1ULL << pins::kButton;
    cfg.mode = GPIO_MODE_INPUT;
    cfg.pull_up_en = GPIO_PULLUP_ENABLE;
    cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    cfg.intr_type = GPIO_INTR_DISABLE;
    ESP_RETURN_ON_ERROR(gpio_config(&cfg), kTag, "gpio");

    g_events = xQueueCreate(kQueueLength, sizeof(ButtonEvent));
    ESP_RETURN_ON_FALSE(g_events != nullptr, ESP_ERR_NO_MEM, kTag, "queue");

    esp_timer_create_args_t args{};
    args.callback = poll;
    args.arg = nullptr;
    args.dispatch_method = ESP_TIMER_TASK;
    args.name = "button";
    args.skip_unhandled_events = true;
    ESP_RETURN_ON_ERROR(esp_timer_create(&args, &g_timer), kTag, "timer create");
    return esp_timer_start_periodic(g_timer, kPollPeriodUs);
}

std::optional<ButtonEvent> wait(TickType_t timeout)
{
    ButtonEvent event;
    if (g_events != nullptr && xQueueReceive(g_events, &event, timeout) == pdTRUE) {
        return event;
    }
    return std::nullopt;
}

}  // namespace board::button
