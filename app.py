"""Entry point for Vercel, which looks for a FastAPI instance named `app` in this file."""
from emporio_agent.api import create_app

app = create_app()
