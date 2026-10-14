#!/bin/bash
# Re-sign the public Halo IPA on macOS using your own keychain identity/profile.
set -euo pipefail
exec python3 "$(dirname "$0")/ios_resign.py" "$@"
