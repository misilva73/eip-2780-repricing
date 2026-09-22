# Anchor-rate sensitivity of the Summary goal table

Ad-hoc report. Recomputes the dashboard's Summary goal table at anchor rates other than the current `ANCHOR_RATE` of 100 Mgas/s, using the latest archived run `20260921T080820Z_22c2404b9ce3f47c` (window 2026-09-18 → 2026-09-21, suite `22c2404b9ce3f47c`). Nothing in `docs/`, `data/` or the analysis was changed — this is a read-only re-derivation.

## Method

Gas is linear in the anchor: `new_gas = anchor_rate × runtime_ms / 1e3`, rounded up ([scripts/analysis.py](../scripts/analysis.py) `build_new_gas_df`). So each anchor's table is each row's own `runtime_ms` from `data/results.json` rescaled and re-`ceil`ed, then fed through the unmodified `collect_goals` / `included_rows` / `excluded_cases_for` in [scripts/build_site.py](../scripts/build_site.py) — same worst-across-cases-and-params rule, same render-time exclusions (`diff_to_unique_code_jumpdest_contract` and `diff_to_contract`, both resolved for this run since it has the contract variants). Reproducing the 100 Mgas/s table this way matches the rendered `docs/index.html` cell for cell, so the rescaled tables are directly comparable to what the dashboard shows.

Cell colours are the dashboard's: 🟢 at or under the goal, 🟡 up to `GOAL_MID_MARGIN` (25%) over, 🔴 beyond.

## 100 Mgas/s — current

| Goal | Target | besu | erigon | ethrex | geth | nethermind | reth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Transfer to self | 12,000 | 🟡 14,385 | 🟡 13,328 | 🟢 4,459 | 🟡 12,865 | 🟢 5,410 | 🟢 5,527 |
| No-value transfer | 15,000 | 🟡 18,724 | 🟢 14,876 | 🟢 5,914 | 🔴 21,582 | 🟢 10,213 | 🟢 10,792 |
| Transfer | 21,000 | 🔴 41,483 | 🔴 30,820 | 🟢 8,057 | 🔴 29,606 | 🟢 12,843 | 🟢 14,321 |
| No-value transfer to delegated account | 18,000 | 🟡 18,696 | 🟢 12,736 | 🟢 5,251 | 🟡 20,642 | 🟢 10,795 | 🟢 10,020 |
| Transfer to delegated account | 24,000 | 🟡 24,848 | 🟢 18,996 | 🟢 7,426 | 🟡 28,071 | 🟢 12,171 | 🟢 12,788 |

4 red, 8 amber, 18 green.

## 75 Mgas/s

| Goal | Target | besu | erigon | ethrex | geth | nethermind | reth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Transfer to self | 12,000 | 🟢 10,789 | 🟢 9,996 | 🟢 3,344 | 🟢 9,649 | 🟢 4,058 | 🟢 4,145 |
| No-value transfer | 15,000 | 🟢 14,043 | 🟢 11,157 | 🟢 4,435 | 🟡 16,187 | 🟢 7,660 | 🟢 8,094 |
| Transfer | 21,000 | 🔴 31,112 | 🟡 23,115 | 🟢 6,043 | 🟡 22,205 | 🟢 9,632 | 🟢 10,741 |
| No-value transfer to delegated account | 18,000 | 🟢 14,022 | 🟢 9,552 | 🟢 3,938 | 🟢 15,482 | 🟢 8,097 | 🟢 7,515 |
| Transfer to delegated account | 24,000 | 🟢 18,636 | 🟢 14,247 | 🟢 5,569 | 🟢 21,054 | 🟢 9,129 | 🟢 9,591 |

1 red, 3 amber, 26 green.

## 60 Mgas/s

| Goal | Target | besu | erigon | ethrex | geth | nethermind | reth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Transfer to self | 12,000 | 🟢 8,631 | 🟢 7,997 | 🟢 2,675 | 🟢 7,719 | 🟢 3,246 | 🟢 3,316 |
| No-value transfer | 15,000 | 🟢 11,235 | 🟢 8,926 | 🟢 3,548 | 🟢 12,950 | 🟢 6,128 | 🟢 6,475 |
| Transfer | 21,000 | 🟡 24,890 | 🟢 18,492 | 🟢 4,834 | 🟢 17,764 | 🟢 7,706 | 🟢 8,593 |
| No-value transfer to delegated account | 18,000 | 🟢 11,218 | 🟢 7,642 | 🟢 3,151 | 🟢 12,386 | 🟢 6,477 | 🟢 6,012 |
| Transfer to delegated account | 24,000 | 🟢 14,909 | 🟢 11,398 | 🟢 4,456 | 🟢 16,843 | 🟢 7,303 | 🟢 7,673 |

0 red, 1 amber, 29 green.

## 50 Mgas/s

| Goal | Target | besu | erigon | ethrex | geth | nethermind | reth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Transfer to self | 12,000 | 🟢 7,193 | 🟢 6,664 | 🟢 2,230 | 🟢 6,433 | 🟢 2,705 | 🟢 2,764 |
| No-value transfer | 15,000 | 🟢 9,362 | 🟢 7,438 | 🟢 2,957 | 🟢 10,791 | 🟢 5,107 | 🟢 5,396 |
| Transfer | 21,000 | 🟢 20,742 | 🟢 15,410 | 🟢 4,029 | 🟢 14,803 | 🟢 6,422 | 🟢 7,161 |
| No-value transfer to delegated account | 18,000 | 🟢 9,348 | 🟢 6,368 | 🟢 2,626 | 🟢 10,321 | 🟢 5,398 | 🟢 5,010 |
| Transfer to delegated account | 24,000 | 🟢 12,424 | 🟢 9,498 | 🟢 3,713 | 🟢 14,036 | 🟢 6,086 | 🟢 6,394 |

0 red, 0 amber, 30 green.

## Anchor at which each cell reaches its goal

The anchor rate below which that client meets that goal (cell turns green); it turns amber 25% above the listed value. Read down a column for a client's binding constraint — the lowest number in it.

| Goal | Target | besu | erigon | ethrex | geth | nethermind | reth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Transfer to self | 12,000 | 83 | 90 | 269 | 93 | 222 | 217 |
| No-value transfer | 15,000 | 80 | 101 | 254 | 70 | 147 | 139 |
| Transfer | 21,000 | 51 | 68 | 261 | 71 | 164 | 147 |
| No-value transfer to delegated account | 18,000 | 96 | 141 | 343 | 87 | 167 | 180 |
| Transfer to delegated account | 24,000 | 97 | 126 | 323 | 85 | 197 | 188 |

The binding cell throughout is besu on "Transfer" (Non-existent, `VALUE_TRANSFER`), the lowest threshold in the table at 51: it is both the last cell to leave red (at 1.25 × 50.6 ≈ 63) and the last to turn green. So nothing is red at **63 Mgas/s** or below, and the whole table is green at **51 Mgas/s** and below. The next constraint after it is erigon's "Transfer" at 68.

## Which case binds each cell

Unchanged by the anchor — every row is rescaled by the same factor, so the worst case per cell is the same at every rate.

| Goal | besu | erigon | ethrex | geth | nethermind | reth |
| --- | --- | --- | --- | --- | --- | --- |
| Transfer to self | Self (no-value) | Self (no-value) | Self (value) | Self (value) | Self (no-value) | Self (value) |
| No-value transfer | Contract (max code, unique) · 64KiB | Contract (max code, unique) · 64KiB | Contract (max code, unique) · 64KiB | Contract (max code, unique) · 64KiB | Contract (max code, unique) · 64KiB | Contract (max code, unique) · 64KiB |
| Transfer | Non-existent | Non-existent | EOA | Contract (max code, unique) · 64KiB | Non-existent | Contract (max code, unique) · 64KiB |
| No-value transfer to delegated account | Delegated (max code, unique) · 24KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 64KiB |
| Transfer to delegated account | Delegated (max code, unique) · 24KiB | Delegated (max code, unique) · 24KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 24KiB | Delegated (max code, unique) · 64KiB | Delegated (max code, unique) · 64KiB |

## Caveats

- Point estimates only. Confidence intervals scale by the same factor and are not carried here.
- This rescales one run's measurements; it is not a re-analysis. Changing `ANCHOR_RATE` in `analysis.py` for real would also put a step in every Trends gas series — archived runs keep the anchor they were analyzed under and are never rescaled (see the mixed-anchor caveat in [CLAUDE.md](../CLAUDE.md)).
- Targets (12,000 / 15,000 / 21,000 / 18,000 / 24,000) are EIP-2780's own component sums and do not move with the anchor.
