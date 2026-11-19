idf_component_register(
    SRCS
        "src/board.cpp"
        "src/button.cpp"
        "src/button_logic.cpp"
        "src/led.cpp"
        "src/led_logic.cpp"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_gpio
    PRIV_REQUIRES esp_driver_ledc esp_timer
)
