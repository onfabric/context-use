from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn

from context_use.cli import output as out
from context_use.cli.base import BaseCommand, prompt_api_key
from context_use.config import build_ctx, load_config
from context_use.ext.adk.agent.runner import AdkAgentBackend
from context_use.proxy.app import create_proxy_app
from context_use.proxy.background import BackgroundMemoryProcessor
from context_use.proxy.handler import ContextProxy
from context_use.proxy.log import setup_proxy_logging

_PID_PATH = Path.home() / ".config" / "context-use" / "proxy.pid"
_LOG_PATH = Path.home() / ".config" / "context-use" / "proxy.log"


def _parse_upstream_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError(
            "Expected a full upstream URL starting with http:// or https://"
        )
    return value.rstrip("/")


class ProxyCommand(BaseCommand):
    name = "proxy"
    help = "Start the context enrichment proxy server"
    description = (
        "Start a transparent proxy that enriches requests with user context "
        "from your local memory store. The proxy forwards each request to "
        "either a fixed upstream URL from --upstream-url or the client's Host "
        "header, while memories are generated using your OpenAI key. "
        "Only POST /v1/chat/completions requests are enriched; all other "
        "paths are forwarded transparently without modification."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--port",
            type=int,
            default=8080,
            help="Port to listen on (default: 8080)",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="Host to bind to (default: 0.0.0.0)",
        )
        parser.add_argument(
            "--upstream-url",
            type=_parse_upstream_url,
            help="Fixed upstream URL (skips the need for a Host header)",
        )
        parser.add_argument(
            "--background",
            "-b",
            action="store_true",
            help="Run the proxy in the background",
        )
        parser.add_argument(
            "--stop",
            action="store_true",
            help="Stop the background proxy",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        if args.stop:
            self._stop()
            return

        cfg = load_config()
        if not cfg.openai_api_key:
            cfg = prompt_api_key(cfg)
        cfg.ensure_dirs()

        if args.background:
            self._start_background(args)
            return

        default_session_id = str(uuid.uuid4())
        ctx = build_ctx(cfg, llm_mode="sync")
        await ctx.init()

        count = await ctx.count_memories()

        print()
        out.header("context-use proxy")
        out.kv("Memories loaded", f"{count:,}")
        out.kv("Endpoint", f"http://localhost:{args.port}/v1/chat/completions")
        out.kv(
            "Enriched route", "POST /v1/chat/completions (all other paths pass through)"
        )
        out.kv("Upstream URL", args.upstream_url or "request Host header")
        out.kv("Default session ID", default_session_id)
        print()
        out.info("Point your client at this proxy:")
        out.info("")
        if args.upstream_url:
            out.info(
                '  client = OpenAI(base_url="http://localhost:'
                f'{args.port}/v1", api_key="<provider-key>")'
            )
        else:
            out.info(
                '  client = OpenAI(base_url="http://localhost:'
                f'{args.port}/v1", api_key="<provider-key>", '
                'default_headers={"Host": "api.openai.com"})'
            )
        print()

        agent_backend = AdkAgentBackend(
            api_key=cfg.openai_api_key,
            model=cfg.openai_model,
        )
        processor = BackgroundMemoryProcessor(ctx, agent_backend)
        handler = ContextProxy(ctx, processor)
        out.kv("Memory processing", "enabled")

        setup_proxy_logging()

        app = create_proxy_app(
            handler,
            upstream_url=args.upstream_url,
            session_id=default_session_id,
        )

        config = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    def _start_background(self, args: argparse.Namespace) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", args.port)) == 0:
                out.error(
                    f"Port {args.port} is already in use. "
                    "Is a proxy already running? Use --stop to stop it."
                )
                sys.exit(1)

        cu = shutil.which("context-use")
        if cu is None:
            out.error("Could not find the context-use executable in PATH.")
            sys.exit(1)

        cmd: list[str] = [
            cu,
            "proxy",
            "--port",
            str(args.port),
            "--host",
            args.host,
        ]
        if args.upstream_url:
            cmd.extend(["--upstream-url", args.upstream_url])

        _PID_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(_LOG_PATH, "w") as log:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

        _PID_PATH.write_text(str(proc.pid))

        time.sleep(1.5)
        if proc.poll() is not None:
            _PID_PATH.unlink(missing_ok=True)
            out.error(f"Proxy failed to start. Check logs: {_LOG_PATH}")
            sys.exit(1)

        print()
        if args.upstream_url:
            out.success(
                "Proxy started - "
                "http://localhost:"
                f"{args.port}/v1/chat/completions -> {args.upstream_url}"
            )
        else:
            out.success(
                f"Proxy started - http://localhost:{args.port}/v1/chat/completions"
            )
        print()

    def _stop(self) -> None:
        if not _PID_PATH.exists():
            out.error("No background proxy found. Is it running?")
            sys.exit(1)

        pid = int(_PID_PATH.read_text().strip())
        _PID_PATH.unlink()
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            out.warn(f"Process {pid} was not running — PID file removed.")
            sys.exit(1)

        for _ in range(20):
            time.sleep(0.25)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(pid, 9)

        print()
        out.success("Proxy stopped")
        print()
