"""
Implement workaround for EFW library problem where cannot move to next-lowest position.
The workaround is to move to a different position before going to that position.
TODO: Remove this code when EFW library gets fixed!
"""
from threading import Event, Thread
from panoptes.pocs.filterwheel.zwo import FilterWheel as ZWOFilterWheel


class FilterWheel(ZWOFilterWheel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._temp_event = Event()

    def _move_to(self, position):

        diff = self.position - position

        temp_pos = None
        # Check if we need to go via an intermediate position
        if diff in (1, 1 - self._n_positions):  # Problem only when this is True
            # Identify intermediate position
            for temp_pos in range(1, self._n_positions + 1):  # Find a temporary position
                if temp_pos not in (self.position, position):
                    break
            self.logger.debug(f"Moving to position {position} via position {temp_pos}.")

        # Move to the requested position
        thread = Thread(target=self._move_to_async, args=(position, temp_pos))
        thread.start()

        # No need to return anything because everything is handled by the move event
        return

    def _move_to_async(self, position, temp_position=None):
        # Blocking function to move to the new position via the temp position
        self._temp_event.clear()
        if temp_position is not None:
            self._driver_move_to(temp_position, event=self._temp_event)
        self._temp_event.clear()
        self._driver_move_to(position, event=self._temp_event)
        self._move_event.set()  # This lets the main code know the move is finished

    def _driver_move_to(self, position, event):
        # Filterwheel class used 1 based position numbering
        # ZWO EFW driver uses 0 based position numbering
        self._driver.set_position(filterwheel_ID=self._handle,
                                  position=position - 1,
                                  move_event=event,  # The driver sets the event
                                  timeout=self._timeout)
        event.wait()  # Blocking
