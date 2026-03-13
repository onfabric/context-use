from __future__ import annotations

import argparse
import sys

from context_use.cli import output as out
from context_use.cli.base import BaseCommand, require_api_key


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
            "--top-k",
            type=int,
            default=5,
            help="Number of memories to retrieve per request (default: 5)",
        )

    async def execute(self, args: argparse.Namespace) -> None:
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
        out.kv("Top-K", args.top_k)
        print()
        out.info("Point your OpenAI client at this proxy:")
        out.info("")
        out.info(
            '  client = OpenAI(base_url="http://localhost:'
            f'{args.port}/v1", api_key="<provider-key>")'
        )
        print()

        app = create_app(ctx, top_k=args.top_k)
        config = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
