"""Seule passerelle vers le validateur V1 du client (aucune copie du protocole)."""
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from community_protocol import (  # noqa: E402
    PROTOCOL_VERSION, PLATFORM, HEX_SHA256, validate_record,
)
