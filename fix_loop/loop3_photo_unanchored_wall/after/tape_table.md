## Photo tier against tape

Gate 8%. Tape good to about plus or minus 1.3 cm.

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 8% |
|---|---|---|---|---|---|---|---|
| bedroom_1 | ceiling | 297.2 | 305.0 [237.7, 372.3] | +7.8 | +2.6% | yes | PASS |
| bedroom_1 | wall (door) | 365.8 | 363.7 [284.0, 443.3] | -2.1 | -0.6% | yes | PASS |
| bedroom_1 | wall | 391.2 | 334.8 [261.5, 408.1] | -56.4 | -14.4% | yes | FAIL |
| bedroom_2 | ceiling | 297.2 | 305.8 [237.8, 373.8] | +8.6 | +2.9% | yes | PASS |
| bedroom_2 | wall (door) | 388.6 | 392.2 [306.3, 478.1] | +3.6 | +0.9% | yes | PASS |
| bedroom_2 | wall | 363.2 | 374.4 [292.5, 456.4] | +11.2 | +3.1% | yes | PASS |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) | 388.6 | 411.3 [321.2, 501.3] | +22.7 | +5.8% | yes | PASS |
| bedroom_2_repeat | wall | 363.2 | 431.4 [337.0, 525.9] | +68.2 | +18.8% | yes | FAIL |
| kitchen | ceiling | 297.2 | 299.2 [240.9, 357.6] | +2.1 | +0.7% | yes | PASS |
| kitchen | wall (door) | 269.2 | 265.8 [214.0, 317.5] | -3.4 | -1.3% | yes | PASS |
| kitchen | wall | 360.3 | 475.3 [382.8, 567.9] | +115.0 | +31.9% | NO | FAIL |

**8 of 12 within the 8% gate. 11 of 12 tape values inside the stated interval.**

## bedroom_2 against bedroom_2_repeat (cross-device: Moto against Nokia)

| wall | bedroom_2 cm | repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 392.2 | 431.4 | +39.2 | +10.0% |
| 2 (longest first) | 374.4 | 411.3 | +36.9 | +9.9% |

## Adjacency against truth

predicted: [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
truth:     [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
matched 3 of 3; 0 predicted edge(s) not in truth

## Overlap and footprint

overlap 0.0000 m2 (gate: zero)
footprint 75.54 m2 [0.01, 189.39]
rooms placed: 4
