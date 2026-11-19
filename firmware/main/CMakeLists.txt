idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_gpio esp_timer spi_flash
)
