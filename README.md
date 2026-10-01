# netplay-relay

A fork of [libretro/netplay-tunnel-server](https://github.com/libretro/netplay-tunnel-server)
(at `23ddaba`), the RetroArch netplay tunnel ("MITM", "relay") server, for a
**private** relay: one that RetroArch players reach without the public
libretro lobby.

## Why a fork

A relay hands each RetroArch host a random session id. RetroArch publishes that
id only by announcing to the public lobby (`lobby.libretro.com`, hard-coded), and
a client joins with it. With announcing off, nobody can learn the id, so nobody
can join. This fork adds a read-only listing so your own launcher can:

```
GET http://<relay>:<status-port>/sessions
{"sessions": [{"id": "q83vEjRWeJASNFZ4", "host": "192.168.1.146", "since": "2026-10-01T20:30:29+00:00"}]}
```

then join the newest:

```
retroarch --connect=<relay>:55435 --mitm-session=q83vEjRWeJASNFZ4 -L <core> <rom>
```

The host side is stock RetroArch: `netplay_use_mitm_server = "true"`,
`netplay_mitm_server = "custom"`, `netplay_custom_mitm_server = "<relay>:55435"`,
`netplay_public_announce = "false"`, then `--host`.

The tunnel protocol is upstream's, unchanged.

## What changed from upstream

- `GET /sessions` on an optional status port (`--status-port`, off by default): open sessions, newest first; `id` is base64 of the 12-byte session unique, exactly what `--mitm-session` takes. Nothing on that port can create, change or end a session.
- Flags instead of a required `.ini`: `--bind`, `--port`, `--timeout`, `--max-sessions`, `--max-clients`, `--log-level`, `--version`. An `.ini` path as the first argument still works as upstream's did; with no argument at all the defaults below apply (upstream read `<script>.ini`).
- Logs go to stderr (journald under systemd) when run with flags.

Defaults: port 55435, timeout 120 s, 128 sessions, 8 clients per session.

## Run

```
nix run github:imkarrer/netplay-relay -- --bind 0.0.0.0 --port 55435 --status-port 55436
python3 retroarch_tunnel_server.py --status-port 55436      # Python 3.7+, stdlib only
```

Expose the status port only where your players are (LAN, a VPN); it lists who is hosting.

## Test

```
python3 -m unittest -v      # or: nix flake check
```

The tests speak RetroArch 1.22's side of the protocol (`network/netplay/netplay_frontend.c`): a host asks for a session, a client joins it by the listed id, and bytes cross the link both ways.

## License

GPL-3.0, as upstream (`LICENSE`).
