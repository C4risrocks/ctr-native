# How ctr-native works

The pack pipeline (`scripts/build_app_from_3ds.py`) has five stages; each one
has a stage log, an input key, and a JSON progress mode, mirroring experiment
carrier `build_ipa_from_nsp.py`'s layout:

## Stages

0. **discover** — `dm/tools/ncch.py::find_game_files` classifies what is in
   the folder: card images (`.3ds`, `.3dz`, `.cci`) by the `NCSD` magic at
   0x100, CIAs by the CIA magic, AppleDouble junk quietly skipped, unknown
   files collected (not read: bounded header reads only).
1. **identify** — `parse_card_image` reads the partition table (offset/size
   pairs at 0x120, media units of 0x200) and the CXI header of partition 0:
   product code (0x150), version (`0x112`), program id (0x118), geo of the
   plain/logo/ExeFS/RomFS regions, and the NCCH flags byte (0x18F), whose bits
   decide crypto: bit0 `FixedKey`, bit2 `NoCrypto`, table bit5 `NoCrypto`:
   the flags that say "no keys needed" or call `--boot9`.
2. **verify** — when `dm/games/<id>/profile.tsv` pins `verified_md5=`, the
   whole file streams through MD5 with a progress bar; mismatch stops unless
   `--allow-damaged`.
3. **decrypt** (only when needed) — `dm/tools/decrypt.py` writes a copy into
   `<title id>_build/decrypted/` with: menus groups (ExHeader + ExeFS header +
   icon/banner: slot 0x2C chain) vs content groups (.code, RomFS: slot by
   ncchflag[3]); the bootrom key generator `((KeyX rol 2) ⊕ KeyY + C1) ROR 41`;
   the two CTR schemes (version 0/2 = pid|magic at byte 8; version 1 = the
   region-relative offset bottom bytes). Output superblock hashes (which
   Nintendo signs over the cleartext) verify both group keys in the copy.
4. **icon** — SMDH (at ExeFS `icon` 0x2040/0x24C0) large 48-icon (RGB565,
   row-major 8x8 Morton tiles — verified against retail icons; 3dbrew's
   "recursive" note predates their retail layout) → PNG upscales → iconutil.
5. **pack** — `<name>.app` assembled: Info.plist, ad-hoc codesign, launcher
   script with **baked absolute paths and a HOME redirection** — the host
   resolves its paths under `$HOME`, so the launcher points it at the
   sibling sandbox and every settings/nand/sdmc/cache/log write lands
   there. Save data stays across rebuilds: the `.key` reuse check never
   deletes or patches the sandbox.

`--progress json` emits one JSON per line: `stage`/`step`/`progress` with
`frac`/`eta`, `stage_end`, and `say`. Bars otherwise, plain lines behind
pipes, `off` only stage start/ends.

## Fases zakuro-macOS (Rust AOT host, 2026-10-30)

F0..F2' verificadas: see `docs/zakuro-macos.md` (measured KPIs). El pipeline del packer
(+`--host zakuro` default) armó el `.app` autocontenido:

    <name>.app/
      Contents/MacOS/ctr-native   launcher (paths absolutos, HOME -> sandbox hermana)
      Contents/MacOS/zakuro-host  baklava binario del host runtime Rust
      Contents/Resources/game/    <title>.dylib + <title>.hints (AOT 3dsrecomp)

Sandbox hermano `<name>.app.ctr-native/`: settings.toml, savedata, mods,
cheats, shaders y zakuro.log.

## Reuse policy

`<id>_build/` keeps: `decrypted/`, `logs/<stage>.log`. The app's signature
(`ctr-native.key`) covers the ROM hash, zakuro-host stamp, profile pin,
toolkit version and launcher text; unchanged inputs skip everything except
the final code sign. `*` are atomic (tmp+rename); the sandbox is only ever
created, never updated.

## The native goal (Fase 2 sketch)

- `dm/host`: the envelope resolved toward a CTR host of our own
  (services: GSP→GPU, DSP path, APT/FS/HID semantics), the nxnative
  equivalent of a Horizon stand-in but for CTR semantics;
- CPU: ARM11 (`code.bin`, which our decrypted container already exposes
  plaintext) translated on stage: dynarmic-backed first (proven), then an
  static-translated pass keyed per build (the nxnative rewriter shape);
- GPU: PICA200 shader translation pipeline; capture-first (run once with
  capture enabled, translate offline, pre-compile to Metal/Vulkan).
