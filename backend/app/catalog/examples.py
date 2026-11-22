"""Ready-made examples offered on the start page.

An example only fills in the form: the report is always computed from data
fetched during the analysis. The six entries were chosen from a backtest run
on live sources (22.11.2026); `kind` says what that run showed.
"""

from datetime import date

from app.contracts.catalog import Example

EXAMPLES: tuple[Example, ...] = (
    Example(
        label="Pszenica ozima, okolice Inowrocławia, 20 czerwca 2023",
        parcel_id="040704_2.0020.34/2",
        crop_id="winter_wheat",
        analysis_date=date(2023, 6, 20),
        kind="deficit",
    ),
    Example(
        label="Pszenica ozima, okolice Rychwała, 20 czerwca 2023",
        parcel_id="301007_5.0020.453",
        crop_id="winter_wheat",
        analysis_date=date(2023, 6, 20),
        kind="deficit",
    ),
    Example(
        label="Pszenica ozima, okolice Pruszcza Gdańskiego, 20 czerwca 2023",
        parcel_id="220404_2.0003.101/1",
        crop_id="winter_wheat",
        analysis_date=date(2023, 6, 20),
        kind="deficit",
    ),
    Example(
        label="Pszenica ozima, okolice Jasienicy, 20 czerwca 2021",
        parcel_id="240205_2.0013.1472/6",
        crop_id="winter_wheat",
        analysis_date=date(2021, 6, 20),
        kind="no_deficit",
    ),
    Example(
        label="Pszenica ozima, okolice Skawiny, 20 czerwca 2021",
        parcel_id="120611_5.0008.980",
        crop_id="winter_wheat",
        analysis_date=date(2021, 6, 20),
        kind="no_deficit",
    ),
    Example(
        label="Pszenica ozima w spoczynku, okolice Jasienicy, 21 listopada 2026",
        parcel_id="240205_2.0013.1472/6",
        crop_id="winter_wheat",
        analysis_date=date(2026, 11, 21),
        kind="no_deficit",
    ),
)


def list_examples() -> list[Example]:
    return list(EXAMPLES)
