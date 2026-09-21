# Tape table

| clip | share of video | share of kept frames | chunks kept | group | bridges ok/rejected | scale m per SfM unit | runtime s | rooms | walls | openings | footprint m2 | plan.png |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bedroom_1 | 37% | 47% | 8 | 3 | 2/5 | 0.0182, 0.1930, 0.2075 | 507 | 1 | 6 | 0 | 95.24 | runs/after/bedroom_1/plan.png |
| bedroom_2 | 32% | 40% | 5 | 1 | 0/4 | 0.3229 | 375 | 1 | 4 | 0 | 2.26 | runs/after/bedroom_2/plan.png |
| bedroom_2_repeat | 25% | 31% | 5 | 2 | 1/3 | 0.1532, 0.1452 | 318 | 1 | 4 | 0 | 16.43 | runs/after/bedroom_2_repeat/plan.png |
| c00a170fe1 | 56% | 70% | 7 | 5 | 4/2 | 0.2099, 0.2138, 0.0893, 0.0886, 0.0816 | 393 | 1 | 12 | 2 | 4.23 | runs/after/c00a170fe1/plan.png |
| hall | 9% | 11% | 9 | 2 | 1/7 | 0.1000, 0.1660 | 570 | 1 | 4 | 0 | 5.15 | runs/after/hall/plan.png |
| kitchen | 27% | 33% | 4 | 1 | 0/3 | 0.2019 | 326 | 1 | 4 | 0 | 5.71 | runs/after/kitchen/plan.png |

## Predicted against tape

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 3% |
|---|---|---|---|---|---|---|---|
| bedroom_1 | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_1 | wall (door) w3 | 365.8 | 318.6 [-685.3, 1322.5] | -47.2 | -12.9% | yes | FAIL |
| bedroom_1 | wall w4 | 391.2 | 422.0 [-907.7, 1751.7] | +30.8 | +7.9% | yes | FAIL |
| bedroom_2 | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2 | wall (door) w1+w3 | 388.6 | 181.7 [-406.2, 769.7] | -206.9 | -53.2% | yes | FAIL |
| bedroom_2 | wall w2+w4 | 363.2 | 124.3 [-277.8, 526.4] | -238.9 | -65.8% | yes | FAIL |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) w1+w3 | 388.6 | 303.9 [-702.0, 1309.7] | -84.7 | -21.8% | yes | FAIL |
| bedroom_2_repeat | wall w2+w4 | 363.2 | 540.6 [-1248.6, 2329.8] | +177.3 | +48.8% | yes | FAIL |
| hall | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| hall | walls | not scored | irregular open plan | - | - | - | - |
| kitchen | ceiling | 297.2 | 233.9 [73.4, 394.3] | -63.3 | -21.3% | yes | FAIL |
| kitchen | wall (door) w1+w3 | 269.2 | 316.2 [99.4, 533.1] | +47.0 | +17.4% | yes | FAIL |
| kitchen | wall w2+w4 | 360.3 | 180.6 [56.7, 304.4] | -179.7 | -49.9% | NO | FAIL |

## bedroom_2 against bedroom_2_repeat

| wall | bedroom_2 cm | bedroom_2_repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 181.7 | 540.6 | +358.8 | +197.4% |
| 2 (longest first) | 124.3 | 303.9 | +179.6 | +144.5% |
