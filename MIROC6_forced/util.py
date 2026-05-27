import re
from typing import Iterable

PANGEO_CATALOG_URL = "https://storage.googleapis.com/cmip6/pangeo-cmip6.json"


def natural_sort(arr: Iterable[str], /) -> list[str]:
    """
    Sort names like r1i1p1f1, r1i2p1f1 in a natural (numeric) order.
    - r1: Realization (initial condition run),
    - i1: Initialization method,
    - p1: Physical parameters,
    - f1: External forcings.

    Numeric order means that r1i1p1f1 < r2i1p1f1 < r11i1p1f1.

    :param l: list of names to be sorted
    """

    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key):
        return tuple(convert(c) for c in re.split(r"(\d+)", key))

    return sorted(arr, key=alphanum_key)
