# M3, measured

*What `winnow context --audit` reports over the sweep, beside what
`scratch/thinking_price.py` reports over the same sweep in the same run. Recorded so the next run
can tell drift from regression, which it cannot do from a single number: the sample moves.*

---

## Why this is a paired comparison and not a threshold

`02-constraints.md` records the prototype run twice on 2026-09-02, hours apart, over the same
200-file even sweep: **168 qualifying sessions the first time and 160 the second**. Nothing changed
except the corpus, because this machine writes transcripts into `~/.claude/projects` while measuring
it and sessions cross the "no compaction, ≥5 requests" filter in both directions as it does. A fixed
acceptance threshold would therefore be measuring the corpus rather than the tool.

`scratch/paired_sweep.py` runs both sides over one file list, through one filter, in one process, so
that a difference between the two columns is a difference in method and nothing else.

## The run

**2026-09-03, 04:08 UTC.** 200 files swept evenly over 1,049 in `~/.claude/projects`. **162
sessions qualify for the prototype, 163 for the tool, 162 for both.**

Share of the exact window left `unattributed`, per session:

| | n | median | \|median\| | p25 | p75 | within ±15% | negative |
|---|---:|---:|---:|---:|---:|---:|---:|
| prototype (`thinking_price.py`) | 162 | **1.0%** | 3.4% | −1.3% | 4.8% | 148/162 (91.4%) | 60 |
| tool (`winnow context`) | 163 | **0.6%** | 3.3% | −1.8% | 4.5% | 150/163 (92.0%) | 67 |
| tool, on the 162 both qualify | 162 | **0.6%** | 3.3% | −1.8% | 4.5% | 149/162 (92.0%) | 66 |

Against `05-recommendation.md`'s acceptance:

- **Median `unattributed` ≤ 5%** — 0.6%. Holds.
- **No worse than the prototype's** — 0.6% against 1.0%, and 3.3% against 3.4% on the absolute
  median, which is the fairer of the two because a signed median can flatter a wide distribution
  that happens to straddle zero. Holds on both.
- **Within-±15% count no lower than the prototype's** — 149/162 against 148/162 on the paired set,
  92.0% against 91.4%. Holds.
- **Kill criterion (median residual > 15%)** — **did not fire.** 0.6%, and the p75 is 4.5%.

The two composition figures, which are what `02-constraints.md`'s correction predicted:

| | prototype | tool | `02-` correction |
|---|---:|---:|---:|
| prefix, median share of window | 25.2% | 25.1% | ~24% |
| retained reasoning, median share | 14.2% | 14.2% | ~14% |

For comparison, the same sweep with only the visible material priced — M1 and M2's readout — leaves
a median of **43.9%** unattributed. That is the ~40% this milestone was for.

## Where the tool and the prototype differ, and why

They agree to within 0.4 points of median and one session of the ±15% count, which is what should be
expected of two implementations of the same subtraction. The differences that exist are all
deliberate:

**The tool qualifies one more session** (163 to 162). The prototype refuses any session whose prefix
subtraction comes out at or below zero; the tool draws the rest of the tree and says in a note why
there is no prefix node (§C7). One session in this sweep is in that state.

**The tool is negative more often** (67 to 60, and 66 to 60 on the paired set). It prices more of the
window — images by area, attachments by their payload strings rather than their serialised JSON,
sub-agent returns at what came back — so it over-explains more often and under-explains less. The
absolute median moves the right way (3.3% against 3.4%), which is the check that this is precision
rather than bias.

**The tool's classifier is the one that runs the prefix subtraction.** The prototype uses
`prefix_floor.line_tokens`, a simpler walk. Using the tool's own classifier is what makes the books
balance in the tool's own units; using a second one would drift the first time either changed.

## The constant, and why no number here is fitted

`--audit` solves per session for the chars-per-token constant that would zero that session's
residual and prints it beside the words **not applied**. There is no flag that applies it, and
`test_the_audit_changes_no_number_in_the_tree` asserts that asking for the diagnostic moves no row.

Every figure above was produced at the shipped **2.6**. §C10 is the reason: a residual fitted to zero
is zero by construction, and a calibrated constant would silently absorb any category the classifier
missed and then report perfect books over a wrong model. The corpus-level residual-zeroing constant
is 2.57 with an IQR of 2.41–2.75 (`02-constraints.md`), which is *agreement* with 2.6 and is worth
having precisely because 2.6 was not fitted to it.

## Reproducing this

```sh
uv run python proposals/ContextTreemap/scratch/paired_sweep.py 200
```

Reads `~/.claude/projects` and writes nothing. Expect a different session count — that is the point
of recording one here rather than asserting one in a test.
