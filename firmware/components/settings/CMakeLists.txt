idf_component_register(
    SRCS
        "src/device.cpp"
        "src/nvs_store.cpp"
        "src/store.cpp"
    INCLUDE_DIRS "include"
    REQUIRES net nvs_flash telemetry
)
