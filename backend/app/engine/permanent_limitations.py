"""Limitations present in every Report, whatever the data of the analysis.

They say what the Report is not and what its data cannot show, so they never
lower the confidence of a verdict.
"""

from app.contracts.report import Limitation

# Present in every Report, whatever the data.
PERMANENT_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        text="Raport nie jest urzędowym stwierdzeniem suszy rolniczej.",
        affects="all",
        permanent=True,
    ),
    Limitation(
        text="Raport nie ocenia nadmiaru wody: podtopień ani zastoisk.",
        affects="all",
        permanent=True,
    ),
    Limitation(
        text=(
            "Raport nie korzysta z prognozy pogody. Rekomendacje nawadniania wynikają "
            "wyłącznie ze stanu na Datę analizy."
        ),
        affects="recommendations",
        permanent=True,
    ),
    Limitation(
        text=(
            "Publiczne dane o rowach i ciekach są niekompletne. Rów lub ciek, którego nie ma "
            "w danych, nie jest brany pod uwagę w Rekomendacjach. Jeśli masz taki rów na "
            "Działce lub obok niej, uwzględnij go przy planowaniu zatrzymywania wody."
        ),
        affects="recommendations",
        permanent=True,
    ),
    # Weather: where the series comes from and how it compares with rain gauges.
    Limitation(
        text=(
            "Pogoda pochodzi z modelu obliczeniowego dla obszaru o boku ok. 9 km (dla lat do "
            "2016: ok. 25 km), a nie z deszczomierza na polu. Opad z lokalnej burzy może się "
            "różnić od tego, co spadło na Twojej działce."
        ),
        affects="all",
        permanent=True,
    ),
    Limitation(
        text=(
            "W porównaniu z pomiarami IMGW ten model podaje przeciętnie o kilkanaście procent "
            "więcej opadu. Rzeczywisty niedobór wody może być więc większy, niż pokazuje raport."
        ),
        affects="all",
        permanent=True,
    ),
    # Soil: the depth the water balance covers.
    Limitation(
        text=(
            "Bilans obejmuje glebę do głębokości 1 m. Rośliny o głębszych korzeniach mogą "
            "w suchych latach sięgać po wodę z głębszych warstw, czego nie uwzględniamy."
        ),
        affects="all",
        permanent=True,
    ),
)

# Permanent limitations of the simulation; shown with its answers, not in the Report.
SIMULATION_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        text="Symulacja nie korzysta z danych satelitarnych: liczy wyłącznie z bilansu wodnego.",
        affects="multiyear",
        permanent=True,
    ),
    Limitation(
        text=(
            "Symulacja nie ocenia plonu, opłacalności, przydatności gleby ani zmianowania."
        ),
        affects="multiyear",
        permanent=True,
    ),
)
