# Presence sensing with Find Hub tags

Date: 2026-11-23 · Status: **research. The firmware side was built the same day** (a portal switch, off by default; see [`../firmware/architecture.md`](../firmware/architecture.md#bluetooth-tag-scan) and [`../decisions.md`](../decisions.md)); **the service is not written.** Nothing here has been tried on a tag or a board.

Idea: the ClimaSense boards listen for the Bluetooth advertisements of Google Find Hub tags (formerly "Find My Device network") and publish what they hear over MQTT. A separate service on the home network recognises the user's own tags among them and derives "home" or "away", which switches a camera.

## Summary

- **It can work, and Google is not needed while it runs.** A tag's rotating identifier is computed from a secret key stored in the tag and the tag's clock. A service that holds the key computes the same identifiers and compares. Google's servers are needed once, to export the key.
- **The key export is the weak point.** There is no official way to get the key. The unofficial route (GoogleFindMyTools) logs in to the Google account with a browser, uses Google's private interfaces and has open reports of breaking. It is needed again only when a tag is paired anew.
- **The firmware part is small:** a passive scan that keeps frames of one type and publishes identifier and signal strength. It fits the flash. Listening costs heat: an estimated 42 mW at the 30 % of the time chosen, 140 mW continuously, to be measured against the temperature reading. Scanning must pause while the setup portal is open.
- **The recognition exists already, but only inside Home Assistant** (GoogleFindMy-HA, with a fork of Bermuda for room presence). No stand-alone service fed from MQTT was found.
- **First step, without any board:** export the key of one tag and recognise it with a PC's Bluetooth. If the export fails for the tags owned, the rest is moot.
- **The rule "away as soon as any tag is missing" is safe for the camera** (a missing tag switches it on) but turns every tag fault into "away": an empty battery, a tag in a drawer out of range.

## Use case

The phone sometimes stays at work, so it cannot be the presence signal. At least one tag (wallet, key ring) is always carried. Therefore:

- **Home:** every enrolled tag was heard recently by at least one board.
- **Away:** at least one enrolled tag has not been heard for longer than a timeout.
- **Unknown:** no board has reported recently (broker, Wi-Fi or service down). For the camera this should count as away.

## How a tag identifies itself

From Google's Find Hub Network accessory specification, version 1.3 (December 2023), read on 2026-11-23.

| Point | What the specification says |
| --- | --- |
| Frame | Service data for the 16-bit UUID `0xFEAA`, then a frame type byte, a 20-byte identifier and an optional flags byte. 29 bytes in all, so it fits a legacy advertisement. A variant with a 32-byte identifier needs Bluetooth 5 extended advertising. |
| Frame type | `0x40` normally, `0x41` while the tag is in "unwanted tracking protection mode". |
| How often | At least one such frame every 2 seconds, at 0 dBm or more. |
| Identifier | Encrypt a 32-byte block (padding, the exponent 10, the tag's clock with its lowest 10 bits cleared, each twice) with AES-256 under the tag's key. Reduce the result modulo the order of the curve SECP160R1, multiply the curve's base point by it. The x coordinate is the identifier. |
| Rotation | Every 1024 seconds on average; the moment is shifted by a random 1 to 204 seconds. The Bluetooth address changes with it. |
| Clock | A 32-bit counter of seconds inside the tag. The tag should save it at least daily; a resolver is expected to try a window of clock values to allow for drift and for time lost in a power cut. |
| Flags byte | Battery level (normal, low, critically low) and the protection-mode bit, XORed with a byte only the key holder can compute. May be left out. |

**Unwanted tracking protection mode** is what the tags are likely to be in when the phone is at work and they are at home. The specification maps it to the "separated" state of the cross-vendor tracker-detection standard. It is switched on by a command from the owner's side or relayed through the network, not by the tag itself; according to a 2025 analysis of the protocol, Google's server orders it once a tag has been away from its owner for 30 minutes or more and another phone has reported it. Users of the Home Assistant integration below report the mode switching on and off while tags lie at home (cause unknown). While it is on, the frame type is `0x41` and the Bluetooth address stays fixed for 24 hours, but **the identifier keeps rotating as usual**, so recognition works the same in both modes. The scanner must accept both frame types.

## Getting the key

The key (the "ephemeral identity key", 32 bytes) is created by the phone at pairing and stored encrypted in the Google account. The tag gives it back only to a client that already knows a value derived from it, so it cannot be read from the tag.

[GoogleFindMyTools](https://github.com/leonboe1/GoogleFindMyTools) (Python, GPL-3.0) re-implements the phone's side:

1. A Chrome window opens for the Google login and for the phone's screen-lock PIN, which unlocks the account's end-to-end encrypted keys.
2. From that it derives the account's owner key, then decrypts each tracker's key (`retrieve_identity_key` in `NovaApi/ExecuteAction/LocateTracker/decrypt_locations.py`).
3. `FMDNCrypto/eid_generator.py` computes an identifier from key and clock value, as in the table above.

Points to know:

- **It prints neither key nor pairing date as it stands.** [Issue 86](https://github.com/leonboe1/GoogleFindMyTools/issues/86) has a six-line patch that does, written by someone who built exactly this ("FMDN BLE presence detection"), with [example scanner code](https://gist.github.com/HarryR/93c07f679370849e5e32fe7e12aa7610).
- **Not confirmed for a bought tag.** The code does not distinguish makes, but nothing read here shows it working with a particular Chipolo, Pebblebee or Motorola tag.
- **Fragile.** Last commit October 2026, 60 open issues. Reports include the login flow hanging after the PIN, decryption failures after Google rotated account keys (a fix is in the unmerged pull request 114), and Google rejecting the client (`API_KEY_ANDROID_APP_BLOCKED`).
- **It leaves a file with account tokens** (`Auth/secrets.json`). Run it once on a PC, copy only key and pairing date into the service's configuration, and delete or lock away that file.
- **The key is a secret.** Whoever has it can recognise the tag anywhere. It belongs in the service's configuration, never in this (public) repository and not on the boards.
- **Licence.** This repository is MIT; GPL-3.0 code cannot be copied into it. The identifier computation is short enough to write from the specification.

## The tag's clock

The identifier depends on the tag's own counter, and what that counter counts from is not in the specification. The 2025 analysis says seconds since the tag was set up, and the example code above computes identifiers from the pairing date. The Home Assistant integration below does not rely on that: it tries three time bases (Unix time, pairing date, the date its key file was created), and one project reports tags with a pairing date in the 1970s.

The service does not need to know. At enrolment, with the tag next to a board, it tries every possible counter value until one identifier matches. One identifier covers 1024 seconds, so a year is about 31,000 candidates, a matter of seconds to minutes on a PC. Afterwards it keeps a window of a few hours around the expected value and follows the drift.

## What already exists

| Project | What it does | Use here |
| --- | --- | --- |
| [GoogleFindMy-HA](https://github.com/BSkando/GoogleFindMy-HA) (Home Assistant integration, active, release 1.9.0 in November 2026) | Exports the keys with the same one-time browser login and has a resolver that other integrations can ask "whose identifier is this?". Reads battery level and protection mode from advertisements. | The most complete implementation of the recognition, and its documents on the resolver are worth reading before writing one. It needs Home Assistant. |
| [Bermuda, fork by jleinenbach](https://github.com/jleinenbach/bermuda) | Room presence in Home Assistant from Bluetooth proxies, with these tags through the resolver above. The original Bermuda does not support them (request open since June 2026). | The ready-made route if Home Assistant with ESPHome Bluetooth proxies is acceptable. A release candidate of a fork. |
| [GoogleFindMyTools](https://github.com/leonboe1/GoogleFindMyTools) (Python) and a [Go port](https://github.com/mheers/google-find-my-tools-go) | Key export and identifier computation, no scanner. | The export step. |
| OpenMQTTGateway | ESP32 firmware that can publish the raw service data of every advertisement over MQTT. | A way to try the service before ClimaSense firmware exists, on any ESP32 board. |
| ESPresense, Theengs | Do not pass these frames through. | None. |

No stand-alone service that takes identifiers from MQTT and recognises tags was found. That part would be written here.

One thing learned from the Home Assistant integration: several users report **tags ringing** while it polls Google for locations. The design here asks Google nothing while it runs, so it should not cause that; it is a reason to keep the export a one-time step.

## What the boards would publish

The user's wish: every MQTT message carries the identifiers heard around the board.

- **Filter in the firmware:** keep only service data for `0xFEAA` with frame type `0x40` or `0x41`. Publishing every Bluetooth advertisement in range would be many times larger and would log the neighbours' devices for no purpose.
- **Per identifier:** the identifier, frame type, flags byte, strongest signal strength, how many times heard, seconds since last heard. About 110 bytes as JSON; the 24 entries of the table are about 2.7 KB, within the MQTT client's 4 KB buffer. A fixed table, no heap.
- **Whose tags:** all in range, the neighbours' included; the board cannot tell them apart. If only the user's own should appear on MQTT, the service could publish the next expected identifiers of its tags and the boards forward only those; the keys would still stay off the boards. Enrolling a tag needs the unfiltered list once. Not built.
- **Own topic rather than inside the state message** (recommended, `<base>/<id>/ble`): the state message feeds Prometheus, which has no use for a list of hex strings, and a separate message can also be sent at once when a new identifier appears, so an arrival is reported within seconds instead of at the next full minute.
- **A switch in the settings** (portal checkbox), like every run-time setting.

## What scanning costs on the board

Bluetooth is not enabled in the firmware today. Nothing below has been built or measured.

| Point | Finding |
| --- | --- |
| Wi-Fi and scanning together | The ESP32-C6 has one 2.4 GHz radio; Wi-Fi and Bluetooth take turns. Espressif rates "station connected, Bluetooth scanning" as supported and stable. |
| Setup portal | "Access point, Bluetooth scanning" is rated unstable, and ESPHome measured that a continuous scan made a C6's access point impossible to join. **Scanning has to stop while the portal is open.** |
| Scan timing | A scan window that falls into Wi-Fi's turn is cut short. Espressif's advice is a window as long as the interval when power does not matter. No figures for the C6. One ESP-IDF release (5.5.5, on the older ESP32) lost most advertisements with Wi-Fi active, so reception needs a check after every ESP-IDF update. |
| Power and heat | Receiving draws 71 mA, against 17 to 28 mA in the modem sleep the firmware uses now. Estimate: about **14 mW more when listening a tenth of the time, about 140 mW more when listening all the time**. For scale, the whole sensor side was brought down to about 12 mW to protect the SHT45, and the module's 70 to 100 mW sit at the far end of the board. |
| Flash | Measured on the build of 2026-11-23 (`idf.py size-components`): about 280 KB, of which 237 KB are Espressif's Bluetooth controller, 31 KB the NimBLE host with only the observer role, and 3.5 KB our own code. The image is 1.64 MB in a 3 MB slot, 48 % free; no partition change. |
| Memory | About 29 KB of RAM taken at build time, mostly controller code that runs from RAM. What the stack allocates when it starts is not measured. |
| Programming interface | NimBLE with only the observer role; `ble_gap_disc` with `passive = 1`. Extended scanning is off by default and only needed for the 32-byte identifier. Duplicate filtering (`filter_duplicates`) stays off: it filters by address, so a tag whose address is fixed for a day would be reported once (inferred from the options, not tried). |
| Known problems | One fixed (Wi-Fi beacon timeouts with Bluetooth and light sleep, fixed before 6.1.1). No report found of dropped MQTT connections with a connected station and a passive scan on 6.x, and none that confirms it is clean. |

Continuous listening on every board is therefore not the starting point. Listening a tenth to a third of the time is enough for the timeouts below, and the boards cover each other.

**Chosen on 2026-11-23: 30 %** (300 ms of every second), after starting at 10 %. Estimates, with a tag sending every 2 s:

| Listening share | Average wait until a tag is heard | Extra heat |
| --- | --- | --- |
| 10 % | about 20 s | about 14 mW |
| **30 %** | **about 6 s** | **about 42 mW** |
| 50 % | about 3 s | about 70 mW |
| close to 100 % | about 1 s | about 140 mW |

Dropping the Wi-Fi connection between messages to make room for listening was considered and rejected: in modem sleep Wi-Fi needs the radio only for the router's beacons and for sending, while reconnecting takes 1 to 3 s each time, which would delay the arrival message, and the broker would report the board offline in between. A per-board setting for the share (continuous on the board by the entrance) is the next step if 6 s is too slow.

## The service

Subscribes to the boards' topics, holds key and clock state per tag, and publishes one state per tag and one overall.

- **Arrival:** first match from any board. Expect seconds to tens of seconds, depending on how much of the time the boards listen.
- **Leaving:** no match from any board for a timeout. With a tag sending every 2 seconds and a board listening a tenth of the time, the chance of hearing nothing for a minute while the tag is in range is about 4 %, for three minutes about 0.01 %; at the 30 % chosen, about 0.002 % for one minute (own estimates, before Wi-Fi sharing the radio). A timeout of three to five minutes looks right, and can come down once reception is known.
- **Battery:** the flags byte gives the tag's battery level to the key holder, so the service can warn before a tag goes silent.

## Risks

- **A silent tag reads as away.** Empty battery, a tag left in a room no board reaches, a tag whose advertising was paused with its button. The camera switches on while the user is home. More boards and the battery warning reduce it.
- **A tag paired again has a new key** and needs a new export.
- **Replay.** Someone who records a tag's frame can replay it near the boards for up to 17 minutes and make that tag look present. Requiring all tags makes this harder; it is acceptable for a camera, not for a door lock.
- **Leaving with no tag at all** reads as home.
- **Google can end the export route** at any time. Tags already exported keep working.

## Open questions, to settle with a real tag

1. Does the export work for the tags actually owned, and what does the clock count from?
2. Which frame do they send: 20-byte or 32-byte identifier? The second needs extended scanning. The Home Assistant integration's notes say only 20-byte ones have been seen.
3. Do they keep sending these frames while connected to the phone, and how often in practice?
4. Does anything change after days in protection mode?
5. How much does scanning warm the board, and how much scanning does Wi-Fi leave room for?

Questions 1 to 4 need no board: a PC with Bluetooth and the example scanner answers them.

## Sources

- [Find Hub Network accessory specification](https://developers.google.com/nearby/fast-pair/specifications/extensions/fmdn?hl=en), Google, version 1.3
- [GoogleFindMyTools](https://github.com/leonboe1/GoogleFindMyTools), [issue 86](https://github.com/leonboe1/GoogleFindMyTools/issues/86) and its [example scanner](https://gist.github.com/HarryR/93c07f679370849e5e32fe7e12aa7610)
- [Analysis of the protocol](https://petsymposium.org/popets/2025/popets-2025-0147.pdf), PoPETs 2025, paper 0147 (read by a research agent, not checked by hand: clock base, when protection mode is ordered)
- GoogleFindMy-HA: [resolver interface](https://github.com/BSkando/GoogleFindMy-HA/blob/main/docs/Ephemeral_Identifier_Resolver_API.md), [resolver pipeline](https://github.com/BSkando/GoogleFindMy-HA/blob/main/docs/EID_RESOLVER_PIPELINE.md), [Bermuda integration](https://github.com/BSkando/GoogleFindMy-HA/blob/main/docs/BERMUDA_INTEGRATION.md); reports of [mode switching](https://github.com/BSkando/GoogleFindMy-HA/issues/210) and [ringing](https://github.com/BSkando/GoogleFindMy-HA/issues/234)
- [RF coexistence, ESP32-C6](https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32c6/api-guides/coexist.html), ESP-IDF 6.1.1, and Espressif's [coexistence FAQ](https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/coexistence.html)
- Scan timing: [esp-idf issue 18931](https://github.com/espressif/esp-idf/issues/18931); access point and scanning: [esphome issue 22534](https://github.com/esphome/esphome/issues/22534)
- Current: [ESP32-C6 datasheet](https://documentation.espressif.com/esp32-c6_datasheet_en.html), [low-power Wi-Fi guide](https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32c6/api-guides/low-power-mode/low-power-mode-wifi.html)
- NimBLE options: [host Kconfig](https://github.com/espressif/esp-idf/blob/v6.1.1/components/bt/host/nimble/Kconfig.in), [controller Kconfig](https://github.com/espressif/esp-idf/blob/v6.1.1/components/bt/controller/esp32c6/Kconfig.in)
