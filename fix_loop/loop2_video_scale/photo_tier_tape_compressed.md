## Photo tier against tape

Gate 8%. Tape good to about plus or minus 1.3 cm.

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 8% |
|---|---|---|---|---|---|---|---|
| bedroom_1 | ceiling | 297.2 | 320.3 [242.2, 398.5] | +23.2 | +7.8% | yes | PASS |
| bedroom_1 | wall (door) | 365.8 | 367.9 [278.4, 457.3] | +2.1 | +0.6% | yes | PASS |
| bedroom_1 | wall | 391.2 | 437.7 [331.2, 544.1] | +46.5 | +11.9% | yes | FAIL |
| bedroom_2 | ceiling | 297.2 | 316.3 [254.4, 378.2] | +19.1 | +6.4% | yes | PASS |
| bedroom_2 | wall (door) | 388.6 | 393.0 [316.5, 469.5] | +4.4 | +1.1% | yes | PASS |
| bedroom_2 | wall | 363.2 | 366.8 [295.4, 438.2] | +3.6 | +1.0% | yes | PASS |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) | 388.6 | 400.4 [322.5, 478.4] | +11.8 | +3.0% | yes | PASS |
| bedroom_2_repeat | wall | 363.2 | 373.4 [300.7, 446.0] | +10.2 | +2.8% | yes | PASS |
| kitchen | ceiling | 297.2 | 211.3 [169.6, 253.1] | -85.8 | -28.9% | NO | FAIL |
| kitchen | wall (door) | 269.2 | 264.9 [213.3, 316.5] | -4.3 | -1.6% | yes | PASS |
| kitchen | wall | 360.3 | 437.8 [352.5, 523.0] | +77.5 | +21.5% | yes | FAIL |

**8 of 12 within the 8% gate. 11 of 12 tape values inside the stated interval.**

## bedroom_2 against bedroom_2_repeat (cross-device: Moto against Nokia)

| wall | bedroom_2 cm | repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 393.0 | 400.4 | +7.4 | +1.9% |
| 2 (longest first) | 366.8 | 373.4 | +6.6 | +1.8% |

## Adjacency against truth

predicted: [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
truth:     [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
matched 3 of 3; 0 predicted edge(s) not in truth

## Overlap and footprint

overlap 0.0000 m2 (gate: zero)
footprint 79.85 m2 [0.01, 204.23]
rooms placed: 4
