"""The relay's protocol as RetroArch 1.22 speaks it (network/netplay/netplay_frontend.c),
and the session listing a private relay needs for --mitm-session.

    python3 -m unittest -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import socket
import subprocess
import sys
import unittest
from pathlib import Path

import retroarch_tunnel_server as relay

HERE = Path(__file__).resolve().parent
ZEROS = bytes(12)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.port, self.status_port = free_port(), free_port()
        config = relay.Config.from_values(self.port, "127.0.0.1", timeout=5.0, log_level=relay.LogLevel.NONE)
        self.tunnel = relay.TunnelServer(config, relay.Logger(None, relay.LogLevel.NONE))
        self.tasks = [asyncio.create_task(self.tunnel()),
                      asyncio.create_task(relay.StatusServer(self.tunnel, "127.0.0.1", self.status_port)())]
        for _ in range(50):
            try:
                _, w = await asyncio.open_connection("127.0.0.1", self.status_port)
                w.close()
                break
            except OSError:
                await asyncio.sleep(0.02)

    async def asyncTearDown(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.port)

    async def host_session(self):
        """RetroArch host with a MITM server: RATS + zeros asks for a session."""
        r, w = await self.connect()
        w.write(b"RATS" + ZEROS)
        await w.drain()
        reply = await asyncio.wait_for(r.readexactly(16), 5)
        self.assertEqual(reply[:4], b"RATS")
        self.assertNotEqual(reply[4:], ZEROS)
        return r, w, reply[4:]

    async def get(self, path: str) -> tuple[str, dict]:
        r, w = await asyncio.open_connection("127.0.0.1", self.status_port)
        w.write(f"GET {path} HTTP/1.1\r\nHost: relay\r\n\r\n".encode())
        await w.drain()
        raw = await asyncio.wait_for(r.read(), 5)
        w.close()
        head, _, body = raw.partition(b"\r\n\r\n")
        return head.split(b"\r\n")[0].decode(), json.loads(body)

    async def sessions(self) -> list[dict]:
        status, body = await self.get("/sessions")
        self.assertEqual(status, "HTTP/1.0 200 OK")
        return body["sessions"]

    async def test_no_sessions_when_nobody_hosts(self):
        self.assertEqual(await self.sessions(), [])

    async def test_hosted_session_is_listed_with_its_retroarch_id(self):
        _, w, unique = await self.host_session()
        listed = await self.sessions()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], base64.b64encode(unique).decode())
        self.assertEqual(len(listed[0]["id"]), 16)  # 12 bytes, no padding
        self.assertEqual(listed[0]["host"], "127.0.0.1")
        w.close()

    async def test_newest_session_first(self):
        _, w1, first = await self.host_session()
        await asyncio.sleep(1.1)  # "since" has one-second resolution in the listing; order uses the full time
        _, w2, second = await self.host_session()
        ids = [s["id"] for s in await self.sessions()]
        self.assertEqual(ids, [base64.b64encode(second).decode(), base64.b64encode(first).decode()])
        w1.close()
        w2.close()

    async def test_join_by_listed_id_links_and_forwards_both_ways(self):
        host_r, host_w, unique = await self.host_session()
        session_id = base64.b64decode((await self.sessions())[0]["id"])

        # Joiner: retroarch --connect=relay --mitm-session=<id> sends RATS + the id.
        client_r, client_w = await self.connect()
        client_w.write(b"RATS" + session_id)
        await client_w.drain()

        # The relay asks the host to open a link for this client.
        link_req = await asyncio.wait_for(host_r.readexactly(16), 5)
        self.assertEqual(link_req[:4], b"RATL")
        client_unique = link_req[4:]

        link_r, link_w = await self.connect()
        link_w.write(b"RATL" + client_unique)
        await link_w.drain()

        client_w.write(b"hello host")
        await client_w.drain()
        self.assertEqual(await asyncio.wait_for(link_r.readexactly(10), 5), b"hello host")
        link_w.write(b"hi client")
        await link_w.drain()
        self.assertEqual(await asyncio.wait_for(client_r.readexactly(9), 5), b"hi client")

        for w in (client_w, link_w, host_w):
            w.close()

    async def test_unknown_session_is_refused(self):
        r, w = await self.connect()
        w.write(b"RATS" + b"x" * 12)
        await w.drain()
        self.assertEqual(await asyncio.wait_for(r.read(), 5), b"")
        w.close()

    async def test_session_leaves_the_listing_when_the_host_quits(self):
        _, w, _ = await self.host_session()
        self.assertEqual(len(await self.sessions()), 1)
        w.close()
        await w.wait_closed()
        for _ in range(50):
            if not await self.sessions():
                break
            await asyncio.sleep(0.05)
        self.assertEqual(await self.sessions(), [])

    async def test_status_is_read_only(self):
        status, _ = await self.get("/anything")
        self.assertEqual(status, "HTTP/1.0 404 Not Found")
        r, w = await asyncio.open_connection("127.0.0.1", self.status_port)
        w.write(b"POST /sessions HTTP/1.1\r\n\r\n")
        await w.drain()
        self.assertTrue((await asyncio.wait_for(r.read(), 5)).startswith(b"HTTP/1.0 405"))
        w.close()


class CliTests(unittest.TestCase):
    def test_version(self):
        out = subprocess.run([sys.executable, str(HERE / "retroarch_tunnel_server.py"), "--version"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("netplay-relay", out)
        self.assertIn("23ddaba", out)

    def test_bad_port_is_a_config_error(self):
        with self.assertRaises(relay.ConfigError):
            relay.Config.from_values(70000)


if __name__ == "__main__":
    unittest.main()
