# Adding a game (bring-up notes)

A game is a folder in `dm/games/<title id>/`:

    dm/games/<title id>/
      profile.tsv   the dumps verified_md5 pin (see dm/games.py)
      README.md     how the bring-up went: dump, settings, gotchas

Like nxnative, the folder is the whole story: `build_app_from_3ds.py` picks it
up by matching the parsed title ID. A game without a folder still builds: it
builds with a "provisional profile" line in the report
(the build never fails for a missing personal profile).

## Bringing a game up (checklist)

1. Build the app and play ten minutes; the runtime reads its own
   `settings.toml` in the sandbox (menus retocan todo en vivo).
2. Verified dumps: put the No-Intro MD5 in `verified_md5=` — the build then
   verifies your copy each time (cheap 1 GB read, ~2 s on SSD).
3. Note anything surprising in `README.md` here.

Current builder: AOT is obtained automatically from a verified per-title cache;
manual global installation paths above describe historical bring-up only.
