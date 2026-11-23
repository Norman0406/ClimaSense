idf_component_register(
    SRCS
        "src/client.cpp"
        "src/mqtt_settings.cpp"
        "src/payload.cpp"
    INCLUDE_DIRS "include"
    REQUIRES ble diagnostics net sensors
    PRIV_REQUIRES mqtt
)
