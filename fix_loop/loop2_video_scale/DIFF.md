# Fix loop 2: before against after

Both sides ran the same six clips on the same cached reconstructions, so this
compares the change and not two draws from a mapper that is not reproducible.

## Headline

| quantity | before | predicted | after | met |
|---|---|---|---|---|
| clips producing a plan | 3 of 6 | 6 of 6 | **6 of 6** | yes |
| share of frames reaching the plan, sample scan | 30% | 40 to 80% | **70%** | yes |
| share of frames, worst clip | 11% | 40 to 80% | 11% | no |
| median absolute wall error | 54.8% | 8 to 20% | **35.3%** | no |
| worst absolute wall error | 75.6% | under 35% | 65.8% | no |
| walls within the 3% gate | 0 of 6 | 1 to 3 | **0 of 8** | no |
| bedroom_2 against bedroom_2_repeat | 107%, 143% | under 20% | **198%, 145%** | no, worse |
| measured ceiling height | prior on both | 2.6 to 3.3 m measured | prior on 4 of 5 | no |

## Per clip

| clip | before: coverage, bridges, group | after: coverage, bridges, group |
|---|---|---|
| c00a170fe1 | 30%, 2 of 6 accepted, group 2 | **70%, 4 of 6 accepted, group 5** |
| bedroom_1 | 38%, 1 of 7, group 2, no plan | 47%, 2 of 7, group 3, plan |
| bedroom_2 | 40%, 2 of 4, group 3 | 40%, 0 of 4, group 1 |
| bedroom_2_repeat | 28%, 0 of 4, group 1 | 31%, 1 of 4, group 2 |
| kitchen | 33%, 0 of 3, group 1, no plan | 33%, 0 of 3, group 1, plan |
| hall | 11%, 1 of 8, group 2, no plan | 11%, 1 of 8, group 2, plan |

Bridging improved on three clips, stayed flat on two and got worse on one.

## Walls against tape

| room | quantity | tape cm | before cm | after cm | before err | after err |
|---|---|---|---|---|---|---|
| bedroom_1 | wall (door) | 365.8 | no plan | 318.6 | - | -12.9% |
| bedroom_1 | wall | 391.2 | no plan | 422.0 | - | +7.9% |
| bedroom_2 | wall (door) | 388.6 | 120.0 | 181.7 | -69.1% | -53.2% |
| bedroom_2 | wall | 363.2 | 88.7 | 124.3 | -75.6% | -65.8% |
| bedroom_2_repeat | wall (door) | 388.6 | 249.0 | 303.9 | -35.9% | -21.8% |
| bedroom_2_repeat | wall | 363.2 | 216.0 | 540.6 | -40.5% | **+48.8%** |
| kitchen | wall (door) | 269.2 | no plan | 316.2 | - | +17.4% |
| kitchen | wall | 360.3 | no plan | 180.6 | - | -49.9% |

Every wall that had a before number improved except `bedroom_2_repeat`'s second
wall, which went from 40% short to 49% long. Nothing came near the 3% gate.

## Falsifiers that fired

Three of the five written down before the fix:

* **Median wall error stayed above 25%** (35.3%). Declared: "then the dominant
  error is not scale and the diagnosis is wrong."
* **bedroom_2 and its repeat still disagree by more than 25%** per wall, and by
  more than before. Declared: "if it does not, the error is random rather than
  systematic and a prior cannot fix it."
* **Measured ceilings did not converge near 2.97 m.** Four of five rooms still
  report the prior, because the reconstruction never reaches the ceiling.

## Interval sanity, found by this run

The after plans carry bounds like `318.6 [-685.3, 1322.5]` cm. A negative wall
length is not a bound. That is fixed in `cozmo/pipeline/video/intervals.py`
(clamp to a positive floor, label anything wider than its own value an
unreliable measurement), but the fix landed after this snapshot, so the numbers
above are what that code actually produced. Every run from the photo tier
onwards has it.
