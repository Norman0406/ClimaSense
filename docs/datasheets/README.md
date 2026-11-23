# Datasheets

Datasheets the design was derived from, kept here unchanged so that page references in the docs stay valid. They belong to their makers.

| File | Part | Version | Used for | SHA-256 |
|---|---|---|---|---|
| [GDEY0213B74-specification-2021-03-17.pdf](GDEY0213B74-specification-2021-03-17.pdf) | Good Display GDEY0213B74, 2.13" e-paper panel (revision 2.0) | 1.0, 2021-03-17, 37 pages | Drawing and FPC tail (page 7), pin table (page 8), supply and timing (pages 10 and 13), block diagram with pin 1 position (page 28), reference circuit (page 29), glue on the tail, which sets where it may bend (page 35, item 12) | `be295bc1ee7bd035a0f2e15c0f08abbc9c31563da663ced2a37864aa95dbf002` |

Which side of the panel the drawing on page 7 shows is confirmed by Good Display's photos of the panel on its product page, <https://www.good-display.com/product/391.html> (seen 2026-11-23): the front photo shows the round corner mark, the driver chip on the glass ledge, the gold contacts and the tail's larger step exactly as the drawing's main view does; the back photo shows the stiffener over the contacts. So the main view is the display side, and pin 1 is where the drawing marks it.

Where the tail may bend follows from this specification: the silicone glue may reach 1.0 mm onto the back of the tail (page 35, item 12), and the tail is rigid there. The smallest bend radius is not in it; that is in Good Display's usage guidelines: <https://www.good-display.com/news/80.html> (bend 1.0 to 1.5 mm from the glass edge, radius above 0.5 mm, read 2026-11-22).
