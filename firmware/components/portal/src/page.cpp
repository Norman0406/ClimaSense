#include "portal/page.h"

#include <algorithm>

namespace portal {

namespace {

constexpr std::string_view kHead =
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>ClimaSense setup</title><style>"
    "body{font-family:system-ui,sans-serif;max-width:32rem;margin:0 auto;padding:1rem;color:#222;background:#fafafa}"
    "h1{font-size:1.4rem;margin:.2rem 0}.id{color:#666;font-size:.9rem}"
    "label{display:block;margin-top:.9rem;font-weight:600}"
    "input[type=text],input[type=password]{width:100%;box-sizing:border-box;padding:.5rem;font-size:1rem;"
    "border:1px solid #bbb;border-radius:.3rem}"
    ".hint{color:#666;font-size:.85rem;font-weight:400}.err{color:#b00020;font-size:.9rem}"
    ".box{background:#fff;border:1px solid #ddd;border-radius:.4rem;padding:.6rem .8rem;margin:.8rem 0}"
    "ul{padding-left:1.2rem;margin:.3rem 0}button{margin-top:1.2rem;padding:.6rem 1.2rem;font-size:1rem}"
    "details{margin-top:1rem}summary{cursor:pointer;font-weight:600}"
    "footer{margin-top:2rem;color:#888;font-size:.8rem}"
    "</style></head><body>";

constexpr std::string_view kTail = "</body></html>";

const FieldError *error_for(std::span<const FieldError> errors, std::string_view field)
{
    const auto it = std::find_if(errors.begin(), errors.end(), [&](const FieldError &e) { return e.field == field; });
    return it == errors.end() ? nullptr : &*it;
}

void field_error(std::string &out, std::span<const FieldError> errors, std::string_view field)
{
    if (const FieldError *e = error_for(errors, field)) {
        out += "<div class=\"err\">";
        out += html_escape(e->message);
        out += "</div>";
    }
}

void text_input(std::string &out, std::string_view name, std::string_view value, std::string_view extra = {})
{
    out += "<input type=\"text\" name=\"";
    out += name;
    out += "\" id=\"";
    out += name;
    out += "\" value=\"";
    out += html_escape(value);
    out += "\"";
    out += extra;
    out += ">";
}

const char *signal_word(int rssi)
{
    if (rssi >= -60) return "strong";
    if (rssi >= -72) return "good";
    if (rssi >= -82) return "weak";
    return "very weak";
}

}  // namespace

std::string html_escape(std::string_view text)
{
    std::string out;
    out.reserve(text.size());
    for (const char c : text) {
        switch (c) {
        case '&':  out += "&amp;"; break;
        case '<':  out += "&lt;"; break;
        case '>':  out += "&gt;"; break;
        case '"':  out += "&quot;"; break;
        case '\'': out += "&#39;"; break;
        default:   out.push_back(c); break;
        }
    }
    return out;
}

std::string render_settings_page(const PageModel &m)
{
    std::string out;
    out.reserve(6144);
    out += kHead;

    const std::string_view name = m.device != nullptr ? m.device->name.view() : std::string_view{};
    out += "<h1>";
    out += html_escape(name.empty() ? std::string_view("ClimaSense") : name);
    out += "</h1><div class=\"id\">";
    out += html_escape(m.device_id);
    out += "</div>";

    out += "<div class=\"box\">";
    if (m.net != nullptr && !m.net->ssid.empty()) {
        out += m.wifi_connected ? "Connected to <b>" : "Not connected to <b>";
        out += html_escape(m.net->ssid.view());
        out += "</b>.";
    } else {
        out += "No Wi-Fi network set up yet.";
    }
    out += "</div>";

    if (!m.notice.empty()) {
        out += "<div class=\"box err\">";
        out += html_escape(m.notice);
        out += "</div>";
    }
    if (!m.errors.empty()) {
        out += "<div class=\"box err\">Not saved: please correct the fields marked below.</div>";
    }

    out += "<form method=\"post\" action=\"/save\">";

    // Network
    out += "<label for=\"ssid\">Wi-Fi network</label>";
    text_input(out, "ssid", m.net != nullptr ? m.net->ssid.view() : std::string_view{},
               " list=\"networks\" autocomplete=\"off\" maxlength=\"32\"");
    field_error(out, m.errors, field::kSsid);
    out += "<datalist id=\"networks\">";
    for (const auto &ap : m.networks) {
        out += "<option value=\"";
        out += html_escape(ap.ssid);
        out += "\">";
    }
    out += "</datalist>";
    if (!m.networks.empty()) {
        out += "<div class=\"hint\">Nearby: <ul>";
        for (const auto &ap : m.networks) {
            out += "<li>";
            out += html_escape(ap.ssid);
            out += " <span class=\"hint\">(";
            out += signal_word(ap.rssi);
            out += ap.secure ? ")" : ", open)";
            out += "</span></li>";
        }
        out += "</ul><a href=\"/scan\">Search again</a></div>";
    } else {
        out += "<div class=\"hint\">No networks found. <a href=\"/scan\">Search again</a></div>";
    }

    // Password: never echoed.
    out += "<label for=\"password\">Password <span class=\"hint\">";
    out += m.password_stored ? "(leave empty to keep the stored one)" : "";
    out += "</span></label>";
    out += "<input type=\"password\" name=\"password\" id=\"password\" autocomplete=\"off\" maxlength=\"64\">";
    field_error(out, m.errors, field::kPassword);
    out += "<label class=\"hint\"><input type=\"checkbox\" name=\"open\" value=\"1\"> Open network (no password)</label>";

    // Device name
    out += "<label for=\"name\">Device name <span class=\"hint\">(e.g. Living room; empty: the ID above)</span></label>";
    text_input(out, "name", name, " maxlength=\"32\"");
    field_error(out, m.errors, field::kName);

    // Advanced
    const bool advanced_error = error_for(m.errors, field::kCountry) != nullptr ||
                                error_for(m.errors, field::kSntpServer) != nullptr ||
                                error_for(m.errors, field::kTimezone) != nullptr;
    out += advanced_error ? "<details open>" : "<details>";
    out += "<summary>Country, time server, time zone</summary>";
    out += "<label for=\"country\">Wi-Fi country <span class=\"hint\">(two letters, e.g. CH)</span></label>";
    text_input(out, "country", m.net != nullptr ? m.net->country.view() : std::string_view{}, " maxlength=\"2\"");
    field_error(out, m.errors, field::kCountry);
    out += "<label for=\"sntp\">Time server</label>";
    text_input(out, "sntp", m.net != nullptr ? m.net->sntp_server.view() : std::string_view{}, " maxlength=\"63\"");
    field_error(out, m.errors, field::kSntpServer);
    out += "<label for=\"tz\">Time zone <span class=\"hint\">(POSIX TZ string)</span></label>";
    text_input(out, "tz", m.net != nullptr ? m.net->timezone.view() : std::string_view{}, " maxlength=\"63\"");
    field_error(out, m.errors, field::kTimezone);
    out += "</details>";

    out += "<button type=\"submit\">Save and restart</button></form>";

    out += "<footer>Firmware ";
    out += html_escape(m.firmware_version);
    out += ", build ";
    out += html_escape(m.build_id);
    out += ". This setup closes by itself after 10 minutes.</footer>";
    out += kTail;
    return out;
}

std::string render_saved_page(std::string_view display_name, std::string_view ssid)
{
    std::string out;
    out += kHead;
    out += "<h1>Saved</h1><div class=\"box\"><b>";
    out += html_escape(display_name);
    out += "</b> restarts now";
    if (!ssid.empty()) {
        out += " and joins <b>";
        out += html_escape(ssid);
        out += "</b>";
    }
    out += ". This setup network disappears; you can close this page.</div>";
    out += kTail;
    return out;
}

}  // namespace portal
