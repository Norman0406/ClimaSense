idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES board sensors esp_app_format esp_timer spi_flash
)
