"""Japanese MFA G2P and occurrence-locked lexicon helpers."""

from .g2p import MfaG2pClient
from .lexicon import LockedLexicon

__all__ = ["LockedLexicon", "MfaG2pClient"]
