# Fix loop 3: before against after

Same five rooms, same camera originals, same EXIF focal. Only the room fitter changed.

## Headline

| quantity | before | predicted | after | met |
|---|---|---|---|---|
| walls within the 8% gate | 6 of 12 | 7 to 9 | **8 of 12** | yes |
| sides anchored to evidence | 16 of 20 | 19 or 20 | **20 of 20** | yes |
| bedroom_1 long axis | 472.9 cm, +20.9% | 380 to 430 cm, within 10% | 334.8 cm, **-14.4%** | no |
| bedroom_2 long axis | 458.6 cm, +26.3% | 355 to 405 cm, within 10% | **374.4 cm, +3.1%** | yes |
| kitchen long axis | 475.3 cm, +31.9% | **unchanged** | **475.3 cm, +31.9%** | yes |
| tape inside the interval | 10 of 12 | - | 11 of 12 | - |

## Per room

| room | quantity | tape cm | before cm | after cm | before err | after err |
|---|---|---|---|---|---|---|
| bedroom_1 | wall (door) | 365.8 | 363.7 | 363.7 | -0.6% | -0.6% |
| bedroom_1 | wall | 391.2 | 472.9 | 334.8 | +20.9% | **-14.4%** |
| bedroom_2 | wall (door) | 388.6 | 392.2 | 392.2 | +0.9% | +0.9% |
| bedroom_2 | wall | 363.2 | 458.6 | 374.4 | +26.3% | **+3.1%** |
| bedroom_2_repeat | wall (door) | 388.6 | 431.4 | 411.3 | +11.0% | **+5.8%** |
| bedroom_2_repeat | wall | 363.2 | 508.5 | 431.4 | +40.0% | **+18.8%** |
| kitchen | wall (door) | 269.2 | 265.8 | 265.8 | -1.3% | -1.3% |
| kitchen | wall | 360.3 | 475.3 | 475.3 | +31.9% | +31.9% |

Every side that used to be closed at the camera path is now anchored to a dense
band of points. No door-wall axis moved, which is right: those were already on a
wall face and the change does not touch them.

## Unchanged and checked

* adjacency 3 of 3 against truth
* overlap 0.0000 m2, gate is zero
* footprint 89.93 -> 75.54 m2
* Moto against Nokia: +10.9%, +10.0% -> +10.0%, +9.9%

## The video tier inherits this

`fit_single_room` is shared. The video tier was **not** re-run in this loop and
its recorded numbers predate the change. Its rooms are fitted the same way, so
it should improve for the same reason, and that is unmeasured, not claimed.
