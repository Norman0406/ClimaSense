idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES board diagnostics net ota portal sensors settings telemetry esp_app_format nvs_flash esp_timer spi_flash
)
