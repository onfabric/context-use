# /// script
# requires-python = ">=3.12"
# dependencies = ["context_use[disk]"]
# [tool.uv.sources]
# context_use = { path = ".", editable = true }
# ///

"""Quick start demo for context_use.

Usage:
    uv run quickstart.py ~/downloads/chatgpt-export.zip
    uv run quickstart.py ~/downloads/chatgpt-export.zip ~/downloads/instagram-export.zip
"""

import sys

from context_use import ContextUse
from context_use.providers.registry import Provider

if len(sys.argv) < 2:
    print("Usage: uv run quickstart.py <chatgpt-export.zip> [instagram-export.zip]")
    sys.exit(1)

ctx = ContextUse.from_config(
    {
        "storage": {"provider": "disk", "config": {"base_path": "./data"}},
        "db": {"provider": "sqlite", "config": {"path": "./context_use.db"}},
    }
)

# --- ChatGPT ---
chatgpt_path = sys.argv[1]
print(f"Processing ChatGPT archive: {chatgpt_path}")
result = ctx.process_archive(Provider.CHATGPT, chatgpt_path)
print(
    f"  ChatGPT: {result.threads_created} threads from {result.tasks_completed} tasks"
)
if result.errors:
    print(f"  Errors: {result.errors}")

# --- Instagram (optional) ---
if len(sys.argv) > 2:
    instagram_path = sys.argv[2]
    print(f"\nProcessing Instagram archive: {instagram_path}")
    result = ctx.process_archive(Provider.INSTAGRAM, instagram_path)
    print(
        f"  Instagram: {result.threads_created} threads from "
        f"{result.tasks_completed} tasks"
    )
    if result.errors:
        print(f"  Errors: {result.errors}")

print("\nDone! Data stored in ./context_use.db and ./data/")
