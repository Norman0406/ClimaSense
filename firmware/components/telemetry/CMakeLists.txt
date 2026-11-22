idf_component_register(
    SRCS
        "src/client.cpp"
        "src/mqtt_settings.cpp"
        "src/payload.cpp"
    INCLUDE_DIRS "include"
    REQUIRES diagnostics net sensors
    PRIV_REQUIRES esp_event esp_netif esp_timer mqtt
)
