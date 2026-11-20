#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "net/networks.h"
#include "portal/dns_answer.h"
#include "portal/form.h"
#include "portal/page.h"

using ::testing::ElementsAreArray;
using ::testing::HasSubstr;
using ::testing::Not;

namespace {

constexpr std::array<uint8_t, 4> kIp{192, 168, 4, 1};

// A DNS query for `name` with `type`, as a phone would send it.
std::vector<uint8_t> make_query(std::string_view name, uint16_t type, uint16_t flags = 0x0100, uint16_t qdcount = 1)
{
    std::vector<uint8_t> q{0x12, 0x34, static_cast<uint8_t>(flags >> 8), static_cast<uint8_t>(flags),
                           static_cast<uint8_t>(qdcount >> 8), static_cast<uint8_t>(qdcount), 0, 0, 0, 0, 0, 0};
    std::size_t start = 0;
    while (start <= name.size()) {
        const std::size_t dot = std::min(name.find('.', start), name.size());
        q.push_back(static_cast<uint8_t>(dot - start));
        q.insert(q.end(), name.begin() + static_cast<std::ptrdiff_t>(start), name.begin() + static_cast<std::ptrdiff_t>(dot));
        start = dot + 1;
    }
    q.push_back(0);
    q.insert(q.end(), {static_cast<uint8_t>(type >> 8), static_cast<uint8_t>(type), 0x00, 0x01});
    return q;
}

std::optional<std::vector<uint8_t>> answer(const std::vector<uint8_t> &query, std::size_t room = 512)
{
    std::vector<uint8_t> out(room);
    const auto n = portal::build_dns_answer(query, kIp, out);
    if (!n) {
        return std::nullopt;
    }
    out.resize(*n);
    return out;
}

net::NetSettings current_net()
{
    net::NetSettings s;
    s.ssid.set("home");
    s.password.set("old-password");
    s.country.set("CH");
    s.sntp_server.set("ch.pool.ntp.org");
    s.timezone.set("CET-1CEST,M3.5.0,M10.5.0/3");
    return s;
}

bool has_error(const portal::FormResult &r, std::string_view field)
{
    return std::any_of(r.errors.begin(), r.errors.end(), [&](const portal::FieldError &e) { return e.field == field; });
}

}  // namespace

// --- DNS ---------------------------------------------------------------------------------------

TEST(DnsAnswer, AQuestionGetsTheDevicesAddress)
{
    const auto q = make_query("connectivitycheck.gstatic.com", 1);
    const auto a = answer(q);
    ASSERT_TRUE(a);
    ASSERT_EQ(a->size(), q.size() + 16);
    EXPECT_EQ((*a)[0], 0x12);  // same ID
    EXPECT_EQ((*a)[1], 0x34);
    EXPECT_EQ((*a)[2], 0x85);  // response, authoritative, recursion desired copied
    EXPECT_EQ((*a)[3], 0x00);  // no error
    EXPECT_EQ((*a)[5], 1);     // one question
    EXPECT_EQ((*a)[7], 1);     // one answer
    const std::vector<uint8_t> record(a->end() - 16, a->end());
    EXPECT_THAT(record, ElementsAreArray({0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x3C, 0x00, 0x04,
                                          192, 168, 4, 1}));
    EXPECT_TRUE(std::equal(q.begin() + 12, q.end(), a->begin() + 12));  // question copied
}

TEST(DnsAnswer, AaaaQuestionGetsAnEmptyAnswer)
{
    const auto q = make_query("captive.apple.com", 28);
    const auto a = answer(q);
    ASSERT_TRUE(a);
    EXPECT_EQ(a->size(), q.size());
    EXPECT_EQ((*a)[7], 0);     // no answer: the client falls back to IPv4
    EXPECT_EQ((*a)[3] & 0x0F, 0);
}

TEST(DnsAnswer, AdditionalRecordsAreDropped)
{
    auto q = make_query("example.com", 1);
    q[11] = 1;  // ARCOUNT 1: an EDNS OPT record follows
    q.insert(q.end(), {0x00, 0x00, 0x29, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00});
    const auto a = answer(q);
    ASSERT_TRUE(a);
    EXPECT_EQ((*a)[11], 0);
    EXPECT_EQ(a->size(), q.size() - 11 + 16);
}

TEST(DnsAnswer, IgnoresWhatIsNotAPlainQuery)
{
    EXPECT_FALSE(answer(make_query("example.com", 1, 0x8100)));     // a response
    EXPECT_FALSE(answer(make_query("example.com", 1, 0x0900)));     // opcode 1
    EXPECT_FALSE(answer(make_query("example.com", 1, 0x0100, 2)));  // two questions
    EXPECT_FALSE(answer(make_query("example.com", 1, 0x0100, 0)));  // none
}

TEST(DnsAnswer, RejectsMalformedPackets)
{
    const auto q = make_query("example.com", 1);
    EXPECT_FALSE(answer(std::vector<uint8_t>(q.begin(), q.begin() + 11)));  // short header
    EXPECT_FALSE(answer(std::vector<uint8_t>(q.begin(), q.begin() + 16)));  // cut inside the name
    EXPECT_FALSE(answer(std::vector<uint8_t>(q.begin(), q.end() - 2)));     // cut in type/class

    auto pointer = q;
    pointer[12] = 0xC0;  // compression pointer in the question
    EXPECT_FALSE(answer(pointer));

    auto overlong = q;
    overlong[12] = 63;   // label longer than the packet
    EXPECT_FALSE(answer(overlong));
}

TEST(DnsAnswer, NeedsRoomForTheAnswer)
{
    const auto q = make_query("example.com", 1);
    EXPECT_FALSE(answer(q, q.size() + 15));
    EXPECT_TRUE(answer(q, q.size() + 16));
}

// --- URL decoding and form values ----------------------------------------------------------------

TEST(UrlDecode, DecodesPlusAndPercent)
{
    EXPECT_EQ(portal::url_decode("a+b%20c"), "a b c");
    EXPECT_EQ(portal::url_decode("K%C3%BCche"), "Küche");
    EXPECT_EQ(portal::url_decode("100%25"), "100%");
    EXPECT_EQ(portal::url_decode(""), "");
}

TEST(UrlDecode, RejectsBrokenEscapes)
{
    EXPECT_FALSE(portal::url_decode("%"));
    EXPECT_FALSE(portal::url_decode("abc%2"));
    EXPECT_FALSE(portal::url_decode("%G1"));
    EXPECT_FALSE(portal::url_decode("%1g"));
}

TEST(FormValue, FindsDecodedValues)
{
    const std::string_view body = "ssid=Home+Net&password=p%26w&name=&open&na%6De2=x";
    EXPECT_EQ(portal::form_value(body, "ssid").value, "Home Net");
    EXPECT_EQ(portal::form_value(body, "password").value, "p&w");
    const auto name = portal::form_value(body, "name");
    EXPECT_EQ(name.status, portal::FieldStatus::Present);
    EXPECT_EQ(name.value, "");
    EXPECT_EQ(portal::form_value(body, "open").status, portal::FieldStatus::Present);  // no '='
    EXPECT_EQ(portal::form_value(body, "name2").value, "x");                            // encoded key
    EXPECT_EQ(portal::form_value(body, "tz").status, portal::FieldStatus::Missing);
}

TEST(FormValue, FirstOccurrenceWinsAndMalformedIsReported)
{
    EXPECT_EQ(portal::form_value("a=1&a=2", "a").value, "1");
    EXPECT_EQ(portal::form_value("a=%zz", "a").status, portal::FieldStatus::Malformed);
}

// --- Applying the form ---------------------------------------------------------------------------

TEST(ApplyForm, EmptyPasswordKeepsTheStoredOneForTheSameNetwork)
{
    const auto r = portal::apply_form("ssid=home&password=&name=Kitchen", current_net(), {});
    ASSERT_TRUE(r.ok());
    EXPECT_EQ(r.net.password.view(), "old-password");
    EXPECT_EQ(r.device.name.view(), "Kitchen");
}

TEST(ApplyForm, NewNetworkNeedsItsPassword)
{
    const auto r = portal::apply_form("ssid=office&password=", current_net(), {});
    EXPECT_TRUE(has_error(r, portal::field::kPassword));

    const auto ok = portal::apply_form("ssid=office&password=new-password", current_net(), {});
    ASSERT_TRUE(ok.ok());
    EXPECT_EQ(ok.net.ssid.view(), "office");
    EXPECT_EQ(ok.net.password.view(), "new-password");
}

TEST(ApplyForm, OpenNetworkClearsThePassword)
{
    const auto r = portal::apply_form("ssid=cafe&password=&open=1", current_net(), {});
    ASSERT_TRUE(r.ok());
    EXPECT_TRUE(r.net.password.empty());

    const auto both = portal::apply_form("ssid=cafe&password=something&open=1", current_net(), {});
    EXPECT_TRUE(has_error(both, portal::field::kPassword));
}

TEST(ApplyForm, PasswordRulesComeFromTheSettings)
{
    const auto r = portal::apply_form("ssid=home&password=short", current_net(), {});
    ASSERT_TRUE(has_error(r, portal::field::kPassword));
    EXPECT_THAT(r.errors[0].message, HasSubstr("8 to 63"));
}

TEST(ApplyForm, CountryIsUpperCasedAndChecked)
{
    const auto r = portal::apply_form("country=de", current_net(), {});
    ASSERT_TRUE(r.ok());
    EXPECT_EQ(r.net.country.view(), "DE");
    EXPECT_TRUE(has_error(portal::apply_form("country=CHE", current_net(), {}), portal::field::kCountry));
    EXPECT_TRUE(has_error(portal::apply_form("country=C", current_net(), {}), portal::field::kCountry));
    EXPECT_TRUE(has_error(portal::apply_form("country=C1", current_net(), {}), portal::field::kCountry));
}

TEST(ApplyForm, TooLongAndMalformedFieldsAreErrors)
{
    const std::string long_ssid = "ssid=" + std::string(33, 'x') + "&password=new-password";
    EXPECT_TRUE(has_error(portal::apply_form(long_ssid, current_net(), {}), portal::field::kSsid));
    EXPECT_TRUE(has_error(portal::apply_form("name=%zz", current_net(), {}), portal::field::kName));
    EXPECT_TRUE(has_error(portal::apply_form("name=%C3", current_net(), {}), portal::field::kName));  // not UTF-8
}

TEST(ApplyForm, MissingFieldsKeepTheirValues)
{
    settings::DeviceSettings device;
    device.name.set("Office");
    const auto r = portal::apply_form("", current_net(), device);
    ASSERT_TRUE(r.ok());
    EXPECT_EQ(r.net.ssid.view(), "home");
    EXPECT_EQ(r.net.password.view(), "old-password");
    EXPECT_EQ(r.device.name.view(), "Office");
}

TEST(ApplyForm, FirstSetupOfAnUnconfiguredDevice)
{
    net::NetSettings blank = current_net();
    blank.ssid.set("");
    blank.password.set("");
    const auto r = portal::apply_form("ssid=home&password=first-password&name=Bedroom", blank, {});
    ASSERT_TRUE(r.ok());
    EXPECT_EQ(r.net.ssid.view(), "home");
    EXPECT_EQ(r.device.name.view(), "Bedroom");
}

// --- Pages ---------------------------------------------------------------------------------------

TEST(Page, EscapesHtml)
{
    EXPECT_EQ(portal::html_escape("<a href=\"x\">'&'</a>"), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
}

TEST(Page, NetworkNamesFromTheScanAreEscaped)
{
    const net::NetSettings net = current_net();
    const settings::DeviceSettings device;
    const std::vector<net::AccessPoint> networks{{"<script>alert(1)</script>", -50, true}};
    portal::PageModel m;
    m.device_id = "climasense-a1b2c3";
    m.net = &net;
    m.device = &device;
    m.networks = networks;
    const std::string page = portal::render_settings_page(m);
    // The hostile name never appears as markup, only escaped.
    EXPECT_THAT(page, Not(HasSubstr("<script>alert(1)")));
    EXPECT_THAT(page, Not(HasSubstr("alert(1)</script>")));
    EXPECT_THAT(page, HasSubstr("&lt;script&gt;alert(1)&lt;/script&gt;"));
    // The page has exactly one script of its own (the firmware upload) and no other.
    std::size_t scripts = 0;
    for (std::size_t at = page.find("<script"); at != std::string::npos; at = page.find("<script", at + 1)) {
        ++scripts;
    }
    EXPECT_EQ(scripts, 1u);
}

TEST(Page, NeverContainsThePassword)
{
    const net::NetSettings net = current_net();
    const settings::DeviceSettings device;
    portal::PageModel m;
    m.net = &net;
    m.device = &device;
    m.password_stored = true;
    const std::string page = portal::render_settings_page(m);
    EXPECT_THAT(page, Not(HasSubstr("old-password")));
    EXPECT_THAT(page, HasSubstr("leave empty to keep the stored one"));
}

TEST(Page, ShowsErrorsAndTheUsersInput)
{
    const auto result = portal::apply_form("ssid=office&password=&name=%22Lab%22", current_net(), {});
    ASSERT_FALSE(result.ok());
    portal::PageModel m;
    m.net = &result.net;
    m.device = &result.device;
    m.errors = result.errors;
    const std::string page = portal::render_settings_page(m);
    EXPECT_THAT(page, HasSubstr("Not saved"));
    EXPECT_THAT(page, HasSubstr("enter the password of the new network"));
    EXPECT_THAT(page, HasSubstr("value=\"office\""));         // the input is kept
    EXPECT_THAT(page, HasSubstr("value=\"&quot;Lab&quot;\"")); // and escaped
}

TEST(Page, SavedPageNamesDeviceAndNetwork)
{
    const std::string page = portal::render_saved_page("Küche <1>", "home");
    EXPECT_THAT(page, HasSubstr("Küche &lt;1&gt;"));
    EXPECT_THAT(page, HasSubstr("joins <b>home</b>"));
}

// --- Network list --------------------------------------------------------------------------------

TEST(Networks, TidyDropsHiddenKeepsStrongestAndSorts)
{
    const auto list = net::tidy_networks({
        {"", -40, true},        // hidden
        {"home", -80, true},
        {"cafe", -70, false},
        {"home", -55, true},    // the stronger "home"
    });
    ASSERT_EQ(list.size(), 2u);
    EXPECT_EQ(list[0].ssid, "home");
    EXPECT_EQ(list[0].rssi, -55);
    EXPECT_EQ(list[1].ssid, "cafe");
    EXPECT_FALSE(list[1].secure);
}

TEST(Networks, TidyKeepsAtMostTwenty)
{
    std::vector<net::AccessPoint> many;
    for (int i = 0; i < 30; ++i) {
        many.push_back({"net" + std::to_string(i), static_cast<int8_t>(-30 - i), true});
    }
    const auto list = net::tidy_networks(many);
    ASSERT_EQ(list.size(), net::kMaxListedNetworks);
    EXPECT_EQ(list.front().ssid, "net0");
}
