## Photo tier against tape

Gate 8%. Tape good to about plus or minus 1.3 cm.

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 8% |
|---|---|---|---|---|---|---|---|
| bedroom_1 | ceiling | 297.2 | 304.7 [230.1, 379.3] | +7.5 | +2.5% | yes | PASS |
| bedroom_1 | wall (door) | 365.8 | 363.7 [275.2, 452.1] | -2.1 | -0.6% | yes | PASS |
| bedroom_1 | wall | 391.2 | 472.9 [357.9, 588.0] | +81.7 | +20.9% | yes | FAIL |
| bedroom_2 | ceiling | 297.2 | 305.8 [230.5, 381.1] | +8.6 | +2.9% | yes | PASS |
| bedroom_2 | wall (door) | 388.6 | 392.2 [296.8, 487.6] | +3.6 | +0.9% | yes | PASS |
| bedroom_2 | wall | 363.2 | 458.6 [347.0, 570.1] | +95.4 | +26.3% | yes | FAIL |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) | 388.6 | 431.4 [326.5, 536.4] | +42.8 | +11.0% | yes | FAIL |
| bedroom_2_repeat | wall | 363.2 | 508.5 [384.9, 632.2] | +145.3 | +40.0% | NO | FAIL |
| kitchen | ceiling | 297.2 | 299.2 [240.9, 357.6] | +2.1 | +0.7% | yes | PASS |
| kitchen | wall (door) | 269.2 | 265.8 [214.0, 317.5] | -3.4 | -1.3% | yes | PASS |
| kitchen | wall | 360.3 | 475.3 [382.8, 567.9] | +115.0 | +31.9% | NO | FAIL |

**6 of 12 within the 8% gate. 10 of 12 tape values inside the stated interval.**

## bedroom_2 against bedroom_2_repeat (cross-device: Moto against Nokia)

| wall | bedroom_2 cm | repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 458.6 | 508.5 | +49.9 | +10.9% |
| 2 (longest first) | 392.2 | 431.4 | +39.2 | +10.0% |

## Adjacency against truth

predicted: [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
truth:     [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
matched 3 of 3; 0 predicted edge(s) not in truth

## Overlap and footprint

overlap 0.0000 m2 (gate: zero)
footprint 89.93 m2 [0.01, 237.50]
rooms placed: 4
