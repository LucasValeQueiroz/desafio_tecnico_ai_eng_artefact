"""Command line entry point: `python -m emporio_agent` starts a conversation."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid

from .agent import ServiceAgent
from .config import ConfigError, load_settings

EXIT_WORDS = {"/sair", "/exit", "/quit"}


def _chat(args: argparse.Namespace) -> int:
    try:
        agent = ServiceAgent.from_settings(load_settings())
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    session_id = args.session or uuid.uuid4().hex[:12]
    print(f"Empório da Música | conversa {session_id} | /sair para encerrar\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break
        reply = agent.reply(session_id, text)
        print(f"\nLia: {reply.text}\n")
        if args.debug:
            print(json.dumps({"tools": reply.tools_used, "guard": reply.guard_flags, "ms": reply.latency_ms}, ensure_ascii=False), file=sys.stderr)
    print(f"Para retomar: python -m emporio_agent --session {session_id}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("emporio_agent.api:create_app", factory=True, host=args.host, port=args.port)
    return 0


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="emporio_agent", description="Empório da Música service agent")
    parser.add_argument("--session", help="Conversation id to resume")
    parser.add_argument("--debug", action="store_true", help="Print consulted tools and safety-net results")
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve", help="Start the HTTP API and chat page")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    return _serve(args) if args.command == "serve" else _chat(args)
