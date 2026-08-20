import json

from pipeline.historical_csv_import import import_olivos_historical_csv


def test_imports_valid_2020_2021_rows_and_skips_bad_rows(tmp_path) -> None:
    source = tmp_path / "olivos.csv"
    source.write_text(
        "Column,number,nombre,doc,fin,entrada,salida,hoja,duracion,dia,hora\n"
        "1,1,PEREZ ANA,30123456,CHALET,2020-03-15T10:15:00Z,2020-03-15T12:00:00Z,PRIVADAS,105,2020-03-15,10\n"
        "2,2,GOMEZ LUIS,28123456,JEFATURA,2021-06-01T09:00:00Z,Turno 24 hs,PRIVADAS,0,2021-06-01,9\n"
        "3,3,FECHA MALA,11111111,CHALET,2020-03-15T10:15:00Z,,PRIVADAS,0,4040-05-26,10\n"
        "4,4,DESFASADO,22222222,CHALET,2020-03-16T10:15:00Z,,PRIVADAS,0,2020-03-15,10\n",
        encoding="utf-8",
    )

    result = import_olivos_historical_csv(source, tmp_path / "data", tmp_path / "public" / "data")

    assert result["imported"] == 2
    assert result["outside_year_range"] == 1
    assert result["entry_date_mismatch"] == 1
    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text(encoding="utf-8"))
    source_entry = manifest["files"]["historical/olivos/datos_olivos-csv.csv"]
    assert source_entry["record_count"] == 2
    assert source_entry["parser"] == "olivos-csv-historico-v1"
    assert (tmp_path / "public" / "data" / "analytics" / "coverage.json").exists()
