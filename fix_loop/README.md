# Fix loop: cross-capture repeatability of LiDAR room segmentation

Contents:

* `DECLARATION.md` the one-page declaration: worst gate, failing number,
  root cause, evidence, intended fix, predicted after number.
* `before/` the official BEFORE run, under the corrected eval. Plans,
  run manifests, debug images, eval output, bench report and a
  `PROVENANCE.txt` naming the commit it was produced at.
* `evidence/` the figures and numbers behind the declaration.
* `regenerate.sh` one command to rebuild either side.

Regenerate:

```bash
fix_loop/regenerate.sh before    # or: after
```

`data/sample` is gitignored and must be present. The script refuses to run
without it rather than producing an empty report.

Order is provable from git history: the eval fix, the BEFORE run, the
evidence and the declaration are separate commits, and `PROVENANCE.txt`
records the commit each run was produced at.
