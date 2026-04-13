"""Allow running as: python -m alpha_omega"""
from .cli import main
raise SystemExit(main() or 0)
