# Sensirion Gas Index Algorithm (vendored)

Turns the SGP41's raw VOC and NOx signals into the VOC index and NOx index.

- Source: https://github.com/Sensirion/gas-index-algorithm
- Version: release 3.2.2 (tag `3.2.2`, commit `12188f5618ca`), fixed-point variant
  (`sensirion_gas_index_algorithm_fixpoint/`), chosen because the ESP32-C6 has no FPU.
- License: BSD 3-Clause, `LICENSE` in this folder (from the repository root).
- **Unchanged.** Do not edit these files; to update, replace them with a newer release and
  update this note. SHA-256 at the time of copying (2026-11-20):

  ```
  bf2f6ec36f568c0e791e361b76d8716be028f69bc432552816645cf64fba0aa3  sensirion_gas_index_algorithm.c
  f53bcfb0277051fcd94974673c9d4be74137f9e69c31eb2a22840bfd0d5c1c5d  sensirion_gas_index_algorithm.h
  cc5044a3eb590ce7d4f653dae3c282c5d0865bf846e8d6e70ecaaf61099562d1  LICENSE
  ```

Used through `sensors/gas_index.h`, which wraps it for C++. Sensirion generated its test data
(`python-wrapper/tests/data/voc.csv`) with the floating-point variant; the unit tests here use
that data with a small tolerance.
