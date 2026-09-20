#!/usr/bin/env python3
"""Print a fresh 48+ char url-safe token for KINETIQ_MCP_PATH_TOKEN."""
import secrets, sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 48
print(secrets.token_urlsafe(n))
