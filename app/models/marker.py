"""Repère posé sur la timeline source : un instant nommé, sans durée."""

from dataclasses import dataclass


@dataclass
class Marker:
    id: str
    position: float
    label: str = ""
