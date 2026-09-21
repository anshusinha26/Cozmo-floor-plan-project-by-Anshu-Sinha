## Photo tier against tape

Gate 8%. Tape good to about plus or minus 1.3 cm.

| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 8% |
|---|---|---|---|---|---|---|---|
| bedroom_1 | ceiling | 297.2 | 303.6 [229.3, 377.9] | +6.4 | +2.2% | yes | PASS |
| bedroom_1 | wall (door) | 365.8 | 402.6 [304.7, 500.6] | +36.8 | +10.1% | yes | FAIL |
| bedroom_1 | wall | 391.2 | 519.3 [393.0, 645.7] | +128.1 | +32.8% | NO | FAIL |
| bedroom_2 | ceiling | 297.2 | 294.8 [222.8, 366.8] | -2.4 | -0.8% | yes | PASS |
| bedroom_2 | wall (door) | 388.6 | 432.4 [327.1, 537.6] | +43.8 | +11.3% | yes | FAIL |
| bedroom_2 | wall | 363.2 | 532.3 [402.8, 661.7] | +169.1 | +46.6% | NO | FAIL |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 [220.0, 320.0] | -27.2 | -9.1% | yes | FAIL |
| bedroom_2_repeat | wall (door) | 388.6 | 431.4 [326.5, 536.4] | +42.8 | +11.0% | yes | FAIL |
| bedroom_2_repeat | wall | 363.2 | 508.5 [384.9, 632.2] | +145.3 | +40.0% | NO | FAIL |
| kitchen | ceiling | 297.2 | 206.2 [161.1, 251.4] | -91.0 | -30.6% | NO | FAIL |
| kitchen | wall (door) | 269.2 | 263.6 [212.2, 314.9] | -5.6 | -2.1% | yes | PASS |
| kitchen | wall | 360.3 | 500.7 [403.2, 598.2] | +140.4 | +39.0% | NO | FAIL |

**3 of 12 within the 8% gate. 7 of 12 tape values inside the stated interval.**

## bedroom_2 against bedroom_2_repeat (cross-device: Moto against Nokia)

| wall | bedroom_2 cm | repeat cm | difference cm | difference % |
|---|---|---|---|---|
| 1 (longest first) | 532.3 | 508.5 | -23.8 | -4.5% |
| 2 (longest first) | 432.4 | 431.4 | -1.0 | -0.2% |

## Adjacency against truth

predicted: [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
truth:     [('bedroom_1', 'hall'), ('bedroom_2', 'hall'), ('hall', 'kitchen')]
matched 3 of 3; 0 predicted edge(s) not in truth

## Overlap and footprint

overlap 0.0000 m2 (gate: zero)
footprint 111.10 m2 [0.01, 304.12]
rooms placed: 4
