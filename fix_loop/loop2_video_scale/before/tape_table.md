# Tape table

| clip | share of video | share of kept frames | chunks kept | group | bridges ok/rejected | scale m per SfM unit | runtime s | rooms | walls | openings | footprint m2 | plan.png |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bedroom_2 | 32% | 40% | 5 | 3 | 2/2 | 0.2190, 0.0746, 0.0532 | 521 | 2 | 8 | 0 | 1.82 | runs/video/bedroom_2/plan.png |
| bedroom_2_repeat | 23% | 28% | 5 | 1 | 0/4 | 0.2011 | 481 | 1 | 4 | 0 | 5.38 | runs/video/bedroom_2_repeat/plan.png |
| c00a170fe1 | 24% | 30% | 7 | 2 | 2/4 | 0.2138, 0.0893 | 479 | 2 | 8 | 0 | 8.66 | runs/video/c00a170fe1/plan.png |

## Predicted against tape

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 3% |
|---|---|---|---|---|---|---|---|
| bedroom_2 | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2 | wall (door) w2+w4 | 388.6 | 120.0 [-41.4, 281.4] | -268.6 | -69.1% | NO | FAIL |
| bedroom_2 | wall w1+w3 | 363.2 | 88.7 [-30.6, 208.0] | -274.5 | -75.6% | NO | FAIL |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) w1+w3 | 388.6 | 249.0 [211.6, 286.4] | -139.6 | -35.9% | NO | FAIL |
| bedroom_2_repeat | wall w2+w4 | 363.2 | 216.0 [183.6, 248.4] | -147.2 | -40.5% | NO | FAIL |

## bedroom_2 against bedroom_2_repeat

| wall | bedroom_2 cm | bedroom_2_repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 120.0 | 249.0 | +129.0 | +107.5% |
| 2 (longest first) | 88.7 | 216.0 | +127.3 | +143.5% |
