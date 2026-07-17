"""Pure selection/navigation logic for the filter (dropdown) bar.

Extracted from app.py so it can be unit-tested: these functions take all
their inputs as arguments and touch no module-level state, no DataFrames,
and no files.
"""


def closest_match(option_list, query, min_len=1):
    # Check prefixes of the query from min_len up to the full length
    for j in range(len(query) + 1, min_len, -1):
        prefix = query[:j]
        # Scan the list and immediately return the first string that contains this prefix
        for option in option_list:
            if option.startswith(prefix):
                return option
            elif prefix in ['31', '32', '41', '42', '43']:
                if option.startswith(prefix[:1]):
                    return option

    return ''  # Return empty string if no valid prefix matches


def first_or_current(options: list[str], current: str | None, bestop=False) -> str:
    # Keep a user's current query value when valid;
    # otherwise the closest option
    # otherwise fall back to the first available option
    # so the page always has a usable selection.
    if current in options:
        return current
    elif bestop and current:
        bestoption = closest_match(options, current)
        if bestoption != '':
            return bestoption

    return options[0] if options else ""


def max_or_current(options: list[str], current: str | None) -> str:
    # Used where the default should be the latest/highest code rather than the
    # first value, such as datatype or closing.
    if current in options:
        return current
    if not options:
        return ""

    return max_value(options)


def max_value(options: list[str]) -> str:
    # Prefer numeric ordering for code-like values, falling back to text order.
    return max(
        options, key=lambda value: (0, int(value)) if value.isdigit() else (1, value)
    )


def previous_next(options: list[str], current: str) -> dict[str, str | None]:
    # Finds the URLs' target values for left/right step buttons.
    if current not in options:
        return {"prev": None, "next": None}

    index = options.index(current)
    return {
        "prev": options[index - 1] if index > 0 else None,
        "next": options[index + 1] if index < len(options) - 1 else None,
    }


def numeric_previous_next(options: list[str], current: str) -> dict[str, str | None]:
    # Numeric step buttons should move by numeric order, not string order
    # ("10" should come after "9", not after "1").
    return previous_next(
        sorted((value for value in options if value.isdigit()), key=int), current
    )


def month_target(
    year: str, month: str, direction: str, *, startyear: int, maxyear: str, maxmonth: str
) -> tuple[str, str] | None:
    # Month navigation wraps across years when the adjacent month is not in the
    # current year's options. Returns None at the edges of the valid range.
    if direction == "prev":
        if month == '01' and year == str(startyear):
            return None
        elif month == '01':
            return str(int(year) - 1), '12'
        else:
            return year, str(int(month) - 1).zfill(2)
    else:
        if month == maxmonth and year == maxyear:
            return None
        elif month == '12':
            return str(int(year) + 1), '01'
        else:
            return year, str(int(month) + 1).zfill(2)
