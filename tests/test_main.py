import os
from unittest.mock import patch

import pytest

from main import load_parts, load_tiers_from_csv, main, scaffold_adapter


@pytest.fixture(autouse=True)
def restore_cwd():
    original = os.getcwd()
    yield
    os.chdir(original)


# --- load_parts ---


def test_load_parts_txt(tmp_path):
    path = tmp_path / "parts.txt"
    path.write_text("PART-001\n# comment\n\nPART-002\n")
    assert load_parts(str(path)) == ["PART-001", "PART-002"]


def test_load_parts_csv_with_header(tmp_path):
    path = tmp_path / "parts.csv"
    path.write_text("part_number,quantity\nP-001,10\nP-002,5\n")
    assert load_parts(str(path)) == ["P-001", "P-002"]


def test_load_parts_csv_no_header(tmp_path):
    path = tmp_path / "parts.csv"
    path.write_text("P-001,10\nP-002,5\n")
    assert load_parts(str(path)) == ["P-001", "P-002"]


def test_load_parts_skips_empty_lines(tmp_path):
    path = tmp_path / "parts.txt"
    path.write_text("P-001\n\n  \nP-002\n")
    assert load_parts(str(path)) == ["P-001", "P-002"]


# --- load_tiers_from_csv ---


def test_load_tiers_returns_engine(tmp_path):
    path = tmp_path / "tiers.csv"
    path.write_text("price_from,price_to,markup_pct,min_order_qty\n0,10,200,1\n")
    engine = load_tiers_from_csv(str(path))
    assert engine is not None
    assert len(engine.tiers) == 1


def test_load_tiers_file_not_found():
    with pytest.raises(SystemExit):
        load_tiers_from_csv("/nonexistent/path.csv")


# --- scaffold_adapter ---


def test_scaffold_creates_file(tmp_path):
    os.chdir(tmp_path)
    scaffold_adapter("test_sup")
    assert (tmp_path / "foxprice" / "adapters" / "test_sup.py").exists()


def test_scaffold_file_contains_class(tmp_path):
    os.chdir(tmp_path)
    scaffold_adapter("my_sup")
    content = (tmp_path / "foxprice" / "adapters" / "my_sup.py").read_text()
    assert "class MySupAdapter" in content
    assert "SUPPLIER_NAME" in content


def test_scaffold_exits_if_exists(tmp_path):
    os.chdir(tmp_path)
    scaffold_adapter("dup_sup")
    with pytest.raises(SystemExit):
        scaffold_adapter("dup_sup")


# --- CLI (main()) ---


def test_main_new_adapter_command(tmp_path):
    os.chdir(tmp_path)
    with patch("sys.argv", ["foxprice", "new-adapter", "cli_sup"]):
        main()
    assert (tmp_path / "foxprice" / "adapters" / "cli_sup.py").exists()


def test_main_run_dry_run(tmp_path):
    (tmp_path / "parts.txt").write_text("P-001\n")
    (tmp_path / "pricing_tiers.csv").write_text(
        "price_from,price_to,markup_pct,min_order_qty\n0,10,200,1\n"
    )
    os.chdir(tmp_path)

    with patch("main.ADAPTERS", []):
        with patch("sys.argv", ["foxprice", "run", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
