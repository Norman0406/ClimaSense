idf_component_register(
    SRCS "src/diagnostics.cpp" "src/log_line.cpp"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_app_format espcoredump log
)
