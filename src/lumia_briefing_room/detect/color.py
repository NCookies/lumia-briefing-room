from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChannelStats:
    r: np.ndarray
    g: np.ndarray
    b: np.ndarray
    v: np.ndarray
    s: np.ndarray


def channel_stats(rgb: np.ndarray) -> ChannelStats:
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = a.max(axis=-1)
    s = v - a.min(axis=-1)
    return ChannelStats(r=r, g=g, b=b, v=v, s=s)


def vivid_mask(stats: ChannelStats, *, v_min: int, s_min: int) -> np.ndarray:
    return (stats.v >= v_min) & (stats.s >= s_min)


def count(mask: np.ndarray) -> int:
    return int(mask.sum())
