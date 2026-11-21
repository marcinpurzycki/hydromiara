"""Indicator files: dekad arithmetic, choice of file per dekad, unpacking script."""

import importlib.util
import zipfile
from datetime import date
from pathlib import Path

import pytest

from app.sources.drought_files import (
    CDI_CLASS_LABELS,
    VALID_CLASSES,
    PointOutsideGridError,
    count_dekads,
    dekad_start,
    index_files,
    next_dekad,
    read_class,
)
from tests.drought_helpers import INSIDE, file_name, write_file

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "unpack_drought_files.py"


def load_script():
    spec = importlib.util.spec_from_file_location("unpack_drought_files", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("day", "start"),
    [
        (date(2023, 6, 1), date(2023, 6, 1)),
        (date(2023, 6, 10), date(2023, 6, 1)),
        (date(2023, 6, 11), date(2023, 6, 11)),
        (date(2023, 6, 20), date(2023, 6, 11)),
        (date(2023, 6, 21), date(2023, 6, 21)),
        (date(2023, 7, 31), date(2023, 7, 21)),
        (date(2024, 2, 29), date(2024, 2, 21)),
    ],
)
def test_dekad_start(day, start):
    assert dekad_start(day) == start


def test_next_dekad_and_count():
    assert next_dekad(date(2023, 6, 1)) == date(2023, 6, 11)
    assert next_dekad(date(2023, 6, 21)) == date(2023, 7, 1)
    assert next_dekad(date(2023, 12, 21)) == date(2024, 1, 1)
    assert count_dekads(date(2023, 1, 1), date(2023, 12, 21)) == 36
    assert count_dekads(date(2023, 6, 11), date(2023, 6, 11)) == 1


def test_every_valid_class_has_a_label():
    assert set(CDI_CLASS_LABELS) == set(VALID_CLASSES)


def test_index_prefers_final_then_version_then_serial(tmp_path):
    first, second, third = date(2026, 1, 21), date(2026, 7, 1), date(2026, 7, 11)
    names = [
        file_name(first, status="p", serial="02"),
        file_name(first, status="z", serial="01"),
        file_name(second, version="410"),
        file_name(second, version="411"),
        file_name(third, serial="01"),
        file_name(third, serial="03"),
        "cdinx_m_edo_20260230_t_411_z01.tif",  # not a date
        "cdinx_m_edo_20260705_t_411_z01.tif",  # not the first day of a dekad
        "README.txt",
    ]
    for name in names:
        (tmp_path / name).touch()

    found = index_files(tmp_path)

    assert list(found) == [first, second, third]
    assert [path.name for path in found.values()] == [names[1], names[3], names[5]]


def test_index_uses_a_provisional_file_when_it_is_the_only_one(tmp_path):
    name = file_name(date(2026, 1, 21), status="p", serial="02")
    (tmp_path / name).touch()

    assert [path.name for path in index_files(tmp_path).values()] == [name]


def test_read_class_at_the_grid_edges(tmp_path):
    path = write_file(tmp_path / file_name(date(2023, 6, 1)), 4)
    west, north, cell = 18.125, 52.791666, 1 / 24

    assert read_class(path, *INSIDE) == 4
    assert read_class(path, west, north) == 4
    with pytest.raises(PointOutsideGridError):
        read_class(path, west + 3 * cell, north)
    with pytest.raises(PointOutsideGridError):
        read_class(path, west, north - 3 * cell)
    with pytest.raises(PointOutsideGridError):
        read_class(path, west - 0.001, north)


def make_archive(directory: Path, name: str, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(directory / name, "w") as bundle:
        for member, content in members.items():
            bundle.writestr(member, content)


def test_unpack_writes_only_indicator_files(tmp_path):
    archives, target = tmp_path / "archives", tmp_path / "out" / "edo"
    archives.mkdir()
    make_archive(
        archives,
        "cdinx_m_edo_20230101_20231221_t.zip",
        {
            "cdinx_m_edo_20230101_t_410_z01.tif": b"one",
            "../cdinx_m_edo_20230111_t_410_z01.tif": b"two",
            "README.txt": b"text",
            "other.tif": b"other",
        },
    )
    make_archive(archives, "unrelated.zip", {"cdinx_m_edo_20230121_t_410_z01.tif": b"x"})
    script = load_script()

    assert script.unpack(archives, target) == (2, 0)
    assert sorted(path.name for path in target.iterdir()) == [
        "cdinx_m_edo_20230101_t_410_z01.tif",
        "cdinx_m_edo_20230111_t_410_z01.tif",
    ]
    assert list(target.parent.iterdir()) == [target]
    assert script.unpack(archives, target) == (0, 2)


def test_unpack_reports_missing_archives(tmp_path, capsys):
    script = load_script()

    assert script.main(["unpack", str(tmp_path), str(tmp_path / "out")]) == 1
    assert "no cdinx_m_edo_*_t.zip archives" in capsys.readouterr().err
