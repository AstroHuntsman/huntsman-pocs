from panoptes.pocs.filterwheel.zwo import FilterWheel as ZWOFilterWheel


class FilterWheel(ZWOFilterWheel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _move_to(self, position):

        # Implement workaround for EFW library problem where cannot move to next-lowest position
        # The workaround is to move to a different position before going to that position
        # TODO: Remove this code when EFW library gets fixed!
        n_filters = len(self._filter_names)
        new_pos_int = self._parse_position(position)
        diff = new_pos_int - self.position
        if diff in (1, 1-n_filters):  # Problem only when this is True
            for temp_pos in range(1, n_filters+1):  # Find a temporary position to move to first
                if temp_pos not in (self.position, position):
                    break
            # Move to the temporary position
            self._driver.set_position(filterwheel_ID=self._handle,
                                      position=self._parse_position(temp_pos) - 1,
                                      move_event=self._move_event,
                                      timeout=self._timeout)

        # Filterwheel class used 1 based position numbering
        # ZWO EFW driver uses 0 based position numbering
        self._driver.set_position(filterwheel_ID=self._handle,
                                  position=self._parse_position(position) - 1,
                                  move_event=self._move_event,
                                  timeout=self._timeout)
