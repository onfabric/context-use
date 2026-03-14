from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from context_use.cli import output as out
from context_use.cli.base import BaseCommand, require_api_key

_PID_PATH = Path.home() / ".config" / "context-use" / "proxy.pid"
_LOG_PATH = Path.home() / ".config" / "context-use" / "proxy.log"


class ProxyCommand(BaseCommand):
    name = "proxy"
    help = "Start the context enrichment proxy server"
    description = (
        "Start an OpenAI-compatible proxy that enriches requests with "
        "user context from your local memory store. Point any OpenAI "
        "SDK at http://localhost:<port>/v1 to get context-enriched "
        "completions via any LLM provider supported by LiteLLM."
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

        if args.background:
            self._start_background(args)
            return

        try:
            import uvicorn

            from context_use.proxy.app import create_app
        except ImportError:
            out.error(
                "Proxy dependencies not installed. Run: pip install context-use[proxy]"
            )
            sys.exit(1)

        from context_use.config import build_ctx, load_config

        cfg = load_config()
        require_api_key(cfg)
        cfg.ensure_dirs()

        ctx = build_ctx(cfg, llm_mode="sync")
        await ctx.init()

        count = await ctx.count_memories()

        print()
        out.header("context-use proxy")
        out.kv("Memories loaded", f"{count:,}")
        out.kv("Endpoint", f"http://localhost:{args.port}/v1/chat/completions")
        print()
        out.info("Point your OpenAI client at this proxy:")
        out.info("")
        out.info(
            '  client = OpenAI(base_url="http://localhost:'
            f'{args.port}/v1", api_key="<provider-key>")'
        )
        print()

        app = create_app(ctx)
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

        cmd: list[str] = [cu, "proxy", "--port", str(args.port), "--host", args.host]

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
        out.success(f"Proxy started — http://localhost:{args.port}/v1/chat/completions")
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
