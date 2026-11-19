idf_component_register(
    SRCS
        "src/bus_scan.cpp"
        "src/esp_i2c_bus.cpp"
        "src/sensor_task.cpp"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_i2c
    PRIV_REQUIRES board esp_timer
)
