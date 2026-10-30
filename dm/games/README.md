# Adding a game (bring-up notes)

A game is a folder in `dm/games/<title id>/`:

    dm/games/<title id>/
      profile.tsv   KEY=VALUE rows of qt-config settings (see dm/games.py KNOWN_KEYS)
      README.md     how the bring-up went: dump, settings, gotchas

Like nxnative, the folder is the whole story: `build_app_from_3ds.py` picks it
up by matching the parsed title ID. A game without a folder still builds: it
gets the shared template only and a "provisional profile" line in the report
(the build never fails for a missing personal profile).

## Bringing a game up (checklist)

1. Try the default template first: build the app, play ten minutes.
2. Stutter at the start? `Renderer.async_shader_compilation=true` (template
   default) covers most of it; check `…/sandbox/user/log/azahar_log.txt`.
3. Wrong shape or want the other screen large? `Layout.layout_option`.
4. Verified dumps: put the No-Intro MD5 in `verified_md5=` — the build then
   verifies your copy each time (cheap 1 GB read, ~2 s on SSD).
5. Note anything surprising in `README.md` here.
