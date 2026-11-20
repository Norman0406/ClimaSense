#include "portal/portal.h"

#include <array>
#include <atomic>
#include <cstdio>
#include <mutex>
#include <string>
#include <vector>

#include "esp_check.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include <unistd.h>

#include "net/wifi.h"
#include "portal/dns_answer.h"
#include "portal/form.h"
#include "portal/page.h"
#include "settings/store.h"

namespace portal {

namespace {

constexpr const char *kTag = "portal";
constexpr uint64_t kRestartDelayUs = 2'000'000;  // lets the "saved" page reach the browser

std::mutex g_lock;              // open() and close() come from the main task and a timer
std::atomic<bool> g_open{false};
Context g_context;
std::vector<net::AccessPoint> g_networks;
std::array<uint8_t, 4> g_ip{};
char g_root_url[24] = {};

httpd_handle_t g_server = nullptr;
esp_timer_handle_t g_close_timer = nullptr;
esp_timer_handle_t g_restart_timer = nullptr;

std::atomic<bool> g_dns_run{false};
std::atomic<bool> g_dns_alive{false};

// --- DNS ------------------------------------------------------------------------------------

void dns_task(void *)
{
    const int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        ESP_LOGE(kTag, "DNS: no socket (errno %d)", errno);
        g_dns_alive = false;
        vTaskDelete(nullptr);
        return;
    }
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(53);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    timeval timeout{1, 0};  // wake up every second to see whether to stop
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    if (bind(sock, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) {
        ESP_LOGE(kTag, "DNS: cannot bind port 53 (errno %d)", errno);
        ::close(sock);  // the socket call, not portal::close()
        g_dns_alive = false;
        vTaskDelete(nullptr);
        return;
    }

    std::array<uint8_t, 512> rx{};
    std::array<uint8_t, 512> tx{};
    while (g_dns_run) {
        sockaddr_in from{};
        socklen_t from_len = sizeof(from);
        const int n = recvfrom(sock, rx.data(), rx.size(), 0, reinterpret_cast<sockaddr *>(&from), &from_len);
        if (n <= 0) {
            continue;  // timeout, or a broken packet
        }
        const auto length = build_dns_answer(std::span<const uint8_t>(rx.data(), static_cast<std::size_t>(n)), g_ip, tx);
        if (length) {
            sendto(sock, tx.data(), *length, 0, reinterpret_cast<sockaddr *>(&from), from_len);
        }
    }
    ::close(sock);  // the socket call, not portal::close()
    g_dns_alive = false;
    vTaskDelete(nullptr);
}

// --- HTTP -----------------------------------------------------------------------------------

esp_err_t send_page(httpd_req_t *req, const std::string &html)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, html.data(), static_cast<ssize_t>(html.size()));
}

PageModel base_model()
{
    PageModel m;
    m.device_id = net::device_id();
    m.firmware_version = g_context.firmware_version;
    m.build_id = g_context.build_id;
    m.wifi_connected = net::connected();
    m.net = &g_context.net;
    m.device = &g_context.device;
    m.password_stored = !g_context.net.password.empty();
    m.networks = g_networks;
    return m;
}

esp_err_t handle_root(httpd_req_t *req)
{
    return send_page(req, render_settings_page(base_model()));
}

esp_err_t handle_scan(httpd_req_t *req)
{
    g_networks = net::scan();
    httpd_resp_set_status(req, "303 See Other");
    httpd_resp_set_hdr(req, "Location", "/");
    return httpd_resp_send(req, "Searching...", HTTPD_RESP_USE_STRLEN);
}

void restart(void *)
{
    ESP_LOGI(kTag, "restarting with the new settings");
    esp_restart();
}

esp_err_t handle_save(httpd_req_t *req)
{
    if (req->content_len > kMaxFormBytes) {
        return httpd_resp_send_err(req, HTTPD_413_CONTENT_TOO_LARGE, "Form too large");
    }
    std::string body(req->content_len, '\0');
    std::size_t received = 0;
    while (received < body.size()) {
        const int n = httpd_req_recv(req, body.data() + received, body.size() - received);
        if (n == HTTPD_SOCK_ERR_TIMEOUT) {
            continue;
        }
        if (n <= 0) {
            return ESP_FAIL;  // connection gone; the server closes it
        }
        received += static_cast<std::size_t>(n);
    }

    const FormResult result = apply_form(body, g_context.net, g_context.device);
    if (!result.ok()) {
        PageModel m = base_model();
        m.net = &result.net;  // the user's input, so it need not be typed again
        m.device = &result.device;
        m.errors = result.errors;
        ESP_LOGI(kTag, "form not saved: %u problem(s)", static_cast<unsigned>(result.errors.size()));
        return send_page(req, render_settings_page(m));
    }

    const auto net_error = settings::save_net(*g_context.store, result.net);
    const auto device_error = settings::save_device(*g_context.store, result.device);
    if (net_error || device_error) {
        PageModel m = base_model();
        m.net = &result.net;
        m.device = &result.device;
        m.notice = "The settings could not be stored (storage error). Please try again.";
        ESP_LOGE(kTag, "storing the settings failed");
        return send_page(req, render_settings_page(m));
    }

    ESP_LOGI(kTag, "settings saved (network \"%s\")", result.net.ssid.c_str());
    const std::string_view name = settings::display_name(result.device, net::device_id());
    const esp_err_t sent = send_page(req, render_saved_page(name, result.net.ssid.view()));
    esp_timer_start_once(g_restart_timer, kRestartDelayUs);
    return sent;
}

// Anything else, including the addresses phones and laptops probe to detect a portal: a
// redirect to the page. With a body, which iOS needs to recognise the portal (as in ESP-IDF's
// captive portal example).
esp_err_t handle_other(httpd_req_t *req, httpd_err_code_t)
{
    httpd_resp_set_status(req, "303 See Other");
    httpd_resp_set_hdr(req, "Location", g_root_url);
    return httpd_resp_send(req, "Redirect to the ClimaSense setup", HTTPD_RESP_USE_STRLEN);
}

esp_err_t start_server()
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_open_sockets = 7;    // phones open several at once while probing
    config.lru_purge_enable = true; // drop the oldest instead of refusing new ones
    config.stack_size = 8192;       // pages are built in the handler
    ESP_RETURN_ON_ERROR(httpd_start(&g_server, &config), kTag, "web server");

    static const httpd_uri_t root{.uri = "/", .method = HTTP_GET, .handler = handle_root, .user_ctx = nullptr};
    static const httpd_uri_t save{.uri = "/save", .method = HTTP_POST, .handler = handle_save, .user_ctx = nullptr};
    static const httpd_uri_t scan{.uri = "/scan", .method = HTTP_GET, .handler = handle_scan, .user_ctx = nullptr};
    httpd_register_uri_handler(g_server, &root);
    httpd_register_uri_handler(g_server, &save);
    httpd_register_uri_handler(g_server, &scan);
    httpd_register_err_handler(g_server, HTTPD_404_NOT_FOUND, handle_other);
    return ESP_OK;
}

void close_timer(void *) { close(); }

// "climasense-a1b2c3" -> "ClimaSense-a1b2c3"
std::string access_point_name()
{
    std::string id = net::device_id();
    const std::size_t dash = id.find('-');
    return "ClimaSense" + (dash == std::string::npos ? std::string("-") + id : id.substr(dash));
}

}  // namespace

esp_err_t open(const Context &context)
{
    std::lock_guard<std::mutex> lock(g_lock);
    if (g_close_timer == nullptr) {
        esp_timer_create_args_t args{};
        args.callback = close_timer;
        args.name = "portal_close";
        ESP_RETURN_ON_ERROR(esp_timer_create(&args, &g_close_timer), kTag, "close timer");
        args.callback = restart;
        args.name = "portal_restart";
        ESP_RETURN_ON_ERROR(esp_timer_create(&args, &g_restart_timer), kTag, "restart timer");
    }
    if (g_open) {
        esp_timer_stop(g_close_timer);
        esp_timer_start_once(g_close_timer, static_cast<uint64_t>(kOpenMinutes) * 60 * 1'000'000);
        ESP_LOGI(kTag, "setup stays open for another %u minutes", static_cast<unsigned>(kOpenMinutes));
        return ESP_OK;
    }
    ESP_RETURN_ON_FALSE(context.store != nullptr, ESP_ERR_INVALID_ARG, kTag, "no settings store");
    g_context = context;

    g_networks = net::scan();  // before the access point: the list is ready for the first page

    const std::string name = access_point_name();
    ESP_RETURN_ON_ERROR(net::start_access_point(name.c_str(), g_ip), kTag, "access point");
    snprintf(g_root_url, sizeof(g_root_url), "http://%u.%u.%u.%u/", g_ip[0], g_ip[1], g_ip[2], g_ip[3]);

    for (int i = 0; i < 30 && g_dns_alive; ++i) {
        vTaskDelay(pdMS_TO_TICKS(100));  // a DNS task from an earlier opening is still ending
    }
    g_dns_run = true;
    g_dns_alive = true;
    if (xTaskCreate(dns_task, "portal_dns", 4096, nullptr, 5, nullptr) != pdPASS) {
        g_dns_alive = false;
        g_dns_run = false;
        net::stop_access_point();
        return ESP_ERR_NO_MEM;
    }
    if (const esp_err_t err = start_server(); err != ESP_OK) {
        g_dns_run = false;
        net::stop_access_point();
        return err;
    }

    esp_timer_start_once(g_close_timer, static_cast<uint64_t>(kOpenMinutes) * 60 * 1'000'000);
    g_open = true;
    ESP_LOGW(kTag, "setup open for %u minutes: join the Wi-Fi network \"%s\" and open %s",
             static_cast<unsigned>(kOpenMinutes), name.c_str(), g_root_url);
    return ESP_OK;
}

void close()
{
    std::lock_guard<std::mutex> lock(g_lock);
    if (!g_open) {
        return;
    }
    g_open = false;
    esp_timer_stop(g_close_timer);
    if (g_server != nullptr) {
        httpd_stop(g_server);
        g_server = nullptr;
    }
    g_dns_run = false;  // the DNS task ends within a second
    net::stop_access_point();
    ESP_LOGI(kTag, "setup closed");
}

bool is_open() { return g_open; }

}  // namespace portal
