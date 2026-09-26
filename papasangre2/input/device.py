"""The phone's orientation - what the accelerometer told the game.

`-[PGEStepsAndSwipeViewController accelerometer:didAccelerate:]` (0x10000b678):
once anything has posted `PGE_INPUT_CheckDeviceRotation` (`checkDeviceRotation:`
0x10000bcd0 sets `needToCheckRotation`, and nothing clears it), every
accelerometer sample with the phone held upright posts `PGE_INPUT_RotateDevice
{orientation: portrait}`, and every one with it held on its side posts
`landscape`.  Lying flat it posts neither.

An agent that `requiresPortraitPicture` or `requiresLandscapePicture` posts
`CheckDeviceRotation` when it is asked to activate, so it hears how the phone
is held at the next sample.  The port has no accelerometer: the orientation is
a state set by a key (decision 1), and "the next sample" is the next pass of
the run loop.  It starts flat - neither - so a level that asks for the phone
to be held up waits for the player to do it (decision 12).
"""

from __future__ import annotations

from ..core.messages import MessageBus

PORTRAIT = 'portrait'
LANDSCAPE = 'landscape'


class Phone:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        #: None (flat), PORTRAIT (upright) or LANDSCAPE (on its side)
        self.orientation: str | None = None
        self.need_to_check_rotation = False
        bus.subscribe('PGE_INPUT_CheckDeviceRotation', self._check_device_rotation)

    def _check_device_rotation(self, _n, _p) -> None:
        self.need_to_check_rotation = True
        self.bus.dispatch_async(self._sample)

    def _sample(self) -> None:
        if self.need_to_check_rotation and self.orientation is not None:
            self.bus.post('PGE_INPUT_RotateDevice', {'orientation': self.orientation})

    def rotate(self, orientation: str | None) -> None:
        """The player holds the phone a new way (a key press)."""
        self.orientation = orientation
        self._sample()
