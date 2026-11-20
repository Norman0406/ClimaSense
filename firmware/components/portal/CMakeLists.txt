idf_component_register(
    SRCS
        "src/dns_answer.cpp"
        "src/form.cpp"
        "src/page.cpp"
        "src/portal.cpp"
    INCLUDE_DIRS "include"
    REQUIRES net settings telemetry
    PRIV_REQUIRES esp_http_server esp_timer lwip
)
