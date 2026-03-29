#!/usr/bin/env python3
"""Convenience wrapper — delegates to the email CLI.

Usage from Claude Code / orchestrator context:
    python3 scripts/email.py inbox
    python3 scripts/email.py search "query"
    python3 scripts/email.py read <id>
    python3 scripts/email.py reply <id> --body "text"
    python3 scripts/email.py send --to addr --subject "subj" --body "text"
"""

import os
import sys
import subprocess

EMAIL_CLI = "/home/fields/samantha-email-agent/email_cli.py"
VENV_PYTHON = "/home/fields/venv/bin/python3"
ENV_FILE = "/home/fields/Fields_Orchestrator/.env"


def main():
    # Load env
    env = os.environ.copy()
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env.setdefault(key, value)

    cmd = [VENV_PYTHON, EMAIL_CLI] + sys.argv[1:]

    result = subprocess.run(
        cmd,
        env=env,
        cwd="/home/fields/samantha-email-agent",
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
