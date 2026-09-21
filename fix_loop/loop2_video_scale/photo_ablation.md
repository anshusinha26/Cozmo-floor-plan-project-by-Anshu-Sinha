# Photo tier: why the camera originals scored worse than the messaging-app copies

## The photographs are identical

Matched by normalised 32x32 correlation, upright:

| room | shots | same picture |
|---|---|---|
| bedroom_1 | 9 | 9 of 9, correlation 1.000 |
| bedroom_2 | 9 | 9 of 9, correlation 1.000 |
| bedroom_2_repeat | 9 | 9 of 9, correlation 1.000 |

Nothing here is about which pictures were taken. `IMG_20260920_123343611.jpg`
is `bedroom2_7.jpeg`, and the order they sort in changes no result.

## The cause: MapAnything was guessing the focal, and guessing long

It works at a 392x518 tensor whatever it is given, so the estimates are directly
comparable. EXIF gives the truth: 2617 px across the 4096 px side is 332 px there.

| photo set | model's focal estimate | implied field of view | error |
|---|---|---|---|
| EXIF ground truth | 332 px | 76 degrees | - |
| compressed 1200x1600 | 283 px | 69 degrees | -15% |
| originals 3072x4096 | 464 px | 46 degrees | **+39%** |
| originals downscaled to 1600 | 464 px | 46 degrees | +39% |

A focal too long means the model thinks it sees a narrower angle than it does,
so it pushes the scene apart sideways by the same factor. Heights are pinned by
the camera-height prior, which is why ceilings stayed right while walls ran 33
to 47% long. The compressed copies scored better only because the guess happened
to land nearer the truth on soft, low resolution images.

## Ablation on bedroom_2

| # | configuration | walls cm | error against tape |
|---|---|---|---|
| a | originals, orientation applied, no EXIF focal | 532.3, 432.4 | +46.6%, +11.3% |
| b | as a, downscaled to 1600 px long side | no change to the focal estimate, 464 px | - |
| c | EXIF focal to Depth Pro only | Depth Pro is not called in this tier, so this is a | no-op |
| d | as a, **EXIF focal given to the reconstruction** | 458.6, 392.2 | **+26.3%, +0.9%** |

Tape 388.6 and 363.2. Downscaling changes nothing: the model normalises to the
same tensor either way. Giving it the focal is the fix.

## Confirmed by the one camera that cannot be fixed

The Nokia 8.1 writes a focal length in millimetres but no 35 mm equivalent, so
it gets no intrinsics and the model still estimates. It is the control:

| room | device | EXIF focal | door wall error | other wall error |
|---|---|---|---|---|
| bedroom_1 | Moto | yes | **-0.6%** | +20.9% |
| bedroom_2 | Moto | yes | **+0.9%** | +26.3% |
| kitchen | Moto | yes | **-1.3%** | +31.9% |
| bedroom_2_repeat | Nokia | **no** | +11.0% | +40.0% |

Every camera that could be told its focal improved; the one that could not did
not. That is the cleanest evidence available that the diagnosis is right.

## What is still wrong

Each room has one wall 21 to 32% long. It is the side the room fitter could not
anchor: three of four sides find a supported wall face, the fourth is closed at
the camera path plus a margin, which is an overestimate whenever the
photographer did not stand against that wall. That is a different defect from
this one and it is not fixed here.
