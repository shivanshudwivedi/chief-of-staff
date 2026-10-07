"""Generate a local hashed-principal registry and private credentials; never overwrite existing files."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/security")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = {name: secrets.token_urlsafe(32) for name in ("operator", "reviewer", "viewer")}
    registry = {
        "principals": [
            {
                "id": name,
                "roles": ["approver" if name == "reviewer" else name],
                "tools": [] if name == "viewer" else ["*"],
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            }
            for name, token in credentials.items()
        ]
    }
    files = {
        "principals.json": json.dumps(registry, indent=2) + "\n",
        "credentials.json": json.dumps(credentials, indent=2) + "\n",
        "security.env": "COS_AUTH_REQUIRED=true\nCOS_AUTH_CONFIG="
        + str(directory / "principals.json")
        + "\nCOS_APPROVAL_SECRET="
        + secrets.token_urlsafe(48)
        + "\n",
    }
    if any((directory / name).exists() for name in files):
        raise SystemExit("Existing security files found; refusing to overwrite credentials")
    for name, contents in files.items():
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(contents)
    print(f"Created private security configuration in {directory}")
    print(
        "Copy security.env values into .env and restart. Give each user only their own token from credentials.json."
    )
    print("Use the workspace settings dialog to enter a principal's token; never use a provider API key.")


if __name__ == "__main__":
    main()
