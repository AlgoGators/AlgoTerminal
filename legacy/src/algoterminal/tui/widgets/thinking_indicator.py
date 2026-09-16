"""A Claude-Code-style "thinking" indicator: a braille spinner paired with a
rotating word and an elapsed-time counter, e.g. "⠙ Backtesting... (3s)".

Drop this in anywhere something takes a beat — an AI agent writing code, a
backtest running, data being pulled — instead of a static "please wait"
string. Mount it in `compose()` (it starts hidden) and toggle `.busy`.
"""

from __future__ import annotations

import random
import time

from textual.widgets import Static

from algoterminal.theme import ORANGE

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Quant/trading-flavored riffs on Claude Code's own "Pondering... / Noodling..."
_WORDS = [
    "Pondering",
    "Noodling",
    "Percolating",
    "Marinating",
    "Ruminating",
    "Crunching numbers",
    "Backtesting",
    "Wrangling data",
    "Chasing alpha",
    "Rebalancing",
    "Simulating fills",
    "Annualizing",
    "Overfitting responsibly",
    "Mean-reverting",
    "Compounding",
    "Fetching ticks",
    "Optimizing Sharpe",
    "Sharpening edges",
    "Bootstrapping",
    "Cooking",
]


class ThinkingIndicator(Static):
    """Animated spinner + rotating word + elapsed timer.

    Starts hidden (`display: none`); set `.busy = True` to show and start
    animating, `.busy = False` to hide and stop.
    """

    DEFAULT_CSS = f"""
    ThinkingIndicator {{
        color: {ORANGE};
        text-style: bold;
        height: auto;
        display: none;
    }}
    """

    def __init__(
        self,
        *args,
        words: list[str] | None = None,
        spin_interval: float = 0.08,
        word_interval: float = 12.0,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._words = words or _WORDS
        self._spin_interval = spin_interval
        self._word_interval = word_interval
        self._frame = 0
        self._word = random.choice(self._words)
        self._started_at = 0.0
        self._spin_timer = None
        self._word_timer = None

    @property
    def busy(self) -> bool:
        return self.display

    @busy.setter
    def busy(self, value: bool) -> None:
        if value:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        if self._spin_timer is not None:
            return  # already running
        self._frame = 0
        self._word = random.choice(self._words)
        self._started_at = time.monotonic()
        self.display = True
        self._render_text()
        self._spin_timer = self.set_interval(self._spin_interval, self._advance_frame)
        self._word_timer = self.set_interval(self._word_interval, self._advance_word)

    def _stop(self) -> None:
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None
        if self._word_timer is not None:
            self._word_timer.stop()
            self._word_timer = None
        self.display = False

    def on_unmount(self) -> None:
        self._stop()

    def _advance_frame(self) -> None:
        self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
        self._render_text()

    def _advance_word(self) -> None:
        choices = [w for w in self._words if w != self._word] or self._words
        self._word = random.choice(choices)

    def _render_text(self) -> None:
        elapsed = int(time.monotonic() - self._started_at)
        glyph = _SPINNER_FRAMES[self._frame]
        self.update(f"{glyph} {self._word}... ({elapsed}s)")
