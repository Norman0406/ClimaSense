idf_component_register(
    SRCS "src/diagnostics.cpp"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_app_format espcoredump log
)
