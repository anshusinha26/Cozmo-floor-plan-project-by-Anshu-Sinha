# How to capture a property

Pick the route that matches your phone. Each one ends with the exact command
to run.

**If you do not have a LiDAR iPhone, take photos rather than video.** Measured
on the same rooms: photographs give a median wall error of 13.0%, video gives
32.9% (`docs/benchmark/eval.json`). Both are still too large to rely on.
Photographs are still the better of the two, because nine deliberate stills
from the corners hold a viewpoint long enough to measure a wall and a walk
does not. Route 3 is the recommended route for a phone without LiDAR.

---

## Route 1. LiDAR, best results

**You need:** an iPhone Pro, iPhone Pro Max or iPad Pro. If your phone has
three camera lenses and a small black circle beside them, it has LiDAR. If you
are not sure, use Route 2.

**Before you start:** install **Stray Scanner** from the App Store. It is
free. Open it once so it can ask for camera permission.

**Recording:**

1. Turn the lights on. Turn ceiling fans off.
2. Open every internal door you want on the plan.
3. Hold the phone **upright (portrait)**. Do not turn it sideways at any point.
4. Press record and **walk slowly and continuously** through every room, and
   back to where you started. One recording for the whole property.
5. Stay **1 to 2.5 metres from the walls**. Closer than 1 m and the sensor
   loses the wall; further than 2.5 m and it gets noisy.
6. In every room, **tilt the phone up once** so the ceiling is in view for a
   few seconds. Without this the ceiling height is reported as a wide guess
   (2.2 to 3.2 m) rather than a measurement.
7. Walk past mirrors and glass without stopping. Do not point at them.
8. Press stop. Recording the whole of a two-bedroom flat takes 3 to 6 minutes.

**Getting it to the computer:** in Stray Scanner, open the recording, tap
share, and send the whole folder (AirDrop to a Mac, or save to Files and copy
it over). The folder is named with a code like `c00a170fe1` and contains
`rgb.mp4`, `depth`, `confidence` and `odometry.csv`. Keep all of it. The
folder can be renamed.

**Run it:**

```bash
uv run cozmo run --input /path/to/your_scan_folder --tier lidar --out runs/my_home
```

---

## Route 2. Video, any phone

**Camera settings:**

* Use the phone's own camera app, video mode.
* **1x lens.** Not 0.5x, not 2x or 3x.
* **1080p or 4K, 30 frames per second.**
* Turn the flash off. Lights on, fans off.

**Recording, one clip per room:**

1. Hold the phone **at chest height, about 1.4 m off the floor**, and keep it
   there. The measurements depend on this height, so a clip shot at waist or
   eye height will be wrong.
2. Hold it **upright (portrait) or sideways (landscape), but do not change
   part-way through a clip.**
3. Stand about **1.5 to 2 m from the walls** and walk a slow loop around the
   room, finishing where you started.
4. Keep both the **floor edge and the ceiling edge** in the frame as you go.
5. **45 to 90 seconds** per room. Slower is better. No fast turns: if the
   picture blurs, you are turning too fast.
6. Stop. Do the next room as a separate clip.

**Getting it to the computer:** put **one clip in one folder per room**, named
after the room:

```
my_home/
  hall/         hall.mov
  bedroom_1/    bedroom_1.mov
  kitchen/      kitchen.mov
```

**Run it, one room at a time:**

```bash
uv run cozmo run --input my_home/bedroom_1 --tier video --out runs/bedroom_1
```

---

## Route 3. Photos, any phone

**Camera settings:** the phone's own camera app, photo mode, **1x lens**,
flash off, lights on.

**Taking them, per room:**

1. Hold the phone at **chest height, about 1.4 m**, as in Route 2. The
   measurements depend on this height.
2. Stand in a **corner and photograph the opposite corner**, with the **floor
   edge and the ceiling edge both visible** in the shot.
3. Do that from **each corner you can reach**: between 2 and 8 photos per
   room. **Nine photos per room is what the measured results came from**, and
   more is better than fewer.
4. **Send the camera originals, not copies.** The pipeline reads the lens
   details the camera writes into each file, and a messaging app strips them.
5. **Stand still for each shot.** A sharp photo from a fixed position is worth
   more than several taken while moving; blur is what costs accuracy here.
6. Take **one extra photo through each doorway**, standing in the doorway
   looking into the next room.
7. Make sure **every wall appears in at least two photos** taken from
   different positions. A wall seen from one position only cannot be measured,
   only guessed at.

**Getting them to the computer:** one folder per room, as in Route 2. Transfer
the **originals** by cable, AirDrop, or a cloud drive. **Do not send them
through WhatsApp, Telegram or any other messaging app**: those recompress
photos and throw away the camera information the pipeline needs.

**Run it, one room at a time:**

```bash
uv run cozmo run --input my_home/bedroom_1 --tier photo --out runs/bedroom_1
```

---

## What to avoid, all routes

* **Do not rotate the phone during a clip or a walk.**
* **Do not change the zoom.** Stay on 1x.
* **Do not use a messaging app to transfer files.**
* **Do not linger on mirrors, glass doors, shower screens or televisions.**
  They show a room that is not there and the pipeline can believe them.
* **Do not capture in the dark.** Lights on, curtains open.
* **Do not let fans, pets or people move through the shot.**
* **Do not move furniture to tidy up, and do not stop half way.** A room
  captured from one side only is reported as partially observed, which is
  honest but less useful than a full loop.
* **Do not shoot each room from the doorway only.** Walk in.

## What good looks like

A capture is good when every wall has been seen from a metre or two away,
every ceiling has been in frame at least once, and you finished where you
started. If you would struggle to draw the room from your own footage, the
pipeline will too.
