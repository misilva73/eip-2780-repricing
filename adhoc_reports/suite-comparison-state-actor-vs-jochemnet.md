# Suite comparison: state-actor vs. jochemnet (2026-08-09 → 2026-08-12)

Ad-hoc comparison, not part of the archived run history in `data/runs/`. Both
suites cover the same date window; values use the same worst-case-per-goal
logic as the dashboard's Summary section (`collect_goals` in
[scripts/build_site.py](scripts/build_site.py)), at the current `ANCHOR_RATE`
(100 Mgas/s).

- **jochemnet** — suite `0d93b5bf3b970403` (jochemnet-glamsterdam-devnet-7-stateful),
  the currently committed run (`data/runs/20260812T025458Z_0d93b5bf3b970403.json`).
- **state-actor** — suite `3f6a0898955dff4f` (state-actor-glamsterdam-devnet-7-stateful),
  fetched/analyzed one-off for this comparison, not archived or committed.

The state-actor suite also includes an `ethrex` client not present in the
jochemnet run; it's omitted below since there's no baseline to diff against.
reth has no fit for either delegated-account goal in the state-actor suite.

## Goal table — state-actor run (`3f6a0898955dff4f`)

| Goal | Target | besu | erigon | geth | nethermind | reth |
|---|---:|---:|---:|---:|---:|---:|
| Transfer to self | 12,000 | 13,926 | 18,016 | 12,040 | 13,929 | 4,290 |
| No-value transfer | 15,000 | 16,549 | 31,416 | 17,492 | 18,644 | 6,976 |
| Transfer | 21,000 | 35,797 | 46,710 | 28,478 | 22,192 | 9,969 |
| No-value transfer to delegated account | 18,000 | 17,754 | 29,435 | 18,114 | 18,392 | — |
| Transfer to delegated account | 24,000 | 23,720 | 42,842 | 25,855 | 20,874 | — |

## % diff vs. jochemnet run (`0d93b5bf3b970403`)

| Goal | besu | erigon | geth | nethermind | reth |
|---|---:|---:|---:|---:|---:|
| Transfer to self | +40.4% | +84.1% | +66.9% | −1.5% | +2.5% |
| No-value transfer | +31.7% | +38.5% | +75.1% | +6.6% | +2.5% |
| Transfer | +17.7% | +17.0% | +46.8% | +36.4% | +3.2% |
| No-value transfer to delegated account | +47.1% | +41.6% | +94.0% | +9.3% | n/a¹ |
| Transfer to delegated account | +55.5% | +68.0% | +116.8% | +33.7% | n/a¹ |

¹ no data in the state-actor run for reth's delegated goals.

## Takeaways

- geth shows the largest, most consistent regression across every goal on the
  state-actor suite (+47% to +117%).
- nethermind is the most stable (−1.5% to +36%); its "Transfer to self" goal
  actually improved slightly.
- `collect_goals` takes the worst across both params and cases per goal, so a
  shift in *which* case is binding (not just how slow it is) can also move a
  cell — e.g. besu's `ZERO_VALUE_TRANSFER` worst case flips from
  `diff_to_contract_diff_max` (jochemnet) to `diff_to_delegated_contract_diff`
  (state-actor).
