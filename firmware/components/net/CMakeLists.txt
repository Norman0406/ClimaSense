idf_component_register(
    SRCS
        "src/settings.cpp"
        "src/wifi.cpp"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_event esp_netif esp_timer esp_wifi
)
