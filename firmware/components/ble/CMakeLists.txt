idf_component_register(
    SRCS
        "src/fhn_frame.cpp"
        "src/scanner.cpp"
        "src/sightings.cpp"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES bt esp_timer
)
