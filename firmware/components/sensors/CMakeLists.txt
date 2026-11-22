idf_component_register(
    SRCS
        "src/bmp580.cpp"
        "src/bus_scan.cpp"
        "src/esp_i2c_bus.cpp"
        "src/scd41.cpp"
        "src/sensor_task.cpp"
        "src/sgp41.cpp"
        "src/sht45.cpp"
        "src/voc_baseline.cpp"
        "vendor/gas_index_algorithm/sensirion_gas_index_algorithm.c"
    INCLUDE_DIRS "include" "vendor/gas_index_algorithm"
    REQUIRES esp_driver_i2c
    PRIV_REQUIRES board esp_timer nvs_flash
)
