import pytest


def test_csv_preserves_leading_zero_ids_and_coordinates(tmp_path):
    from crazy_buffer import read_points_csv, RunReport

    path = tmp_path / "points.csv"
    path.write_text("id,x,y,value\n001,116.4,39.9,3\n", encoding="utf-8")
    report = RunReport()
    result = read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326, report=report)
    assert result.loc[0, "id"] == "001"
    assert result.crs.to_epsg() == 4326
    assert (result.geometry.x.iloc[0], result.geometry.y.iloc[0]) == (116.4, 39.9)
    assert result.loc[0, "value"] == 3
    assert report.steps[-1]["name"] == "read_points_csv"


@pytest.mark.parametrize("identifier", ["", " "])
def test_csv_empty_id_is_not_stringified(tmp_path, identifier):
    from crazy_buffer import read_points_csv, SpatialInputError

    path = tmp_path / "points.csv"
    path.write_text(f"id,x,y\n{identifier},116.4,39.9\n", encoding="utf-8")
    with pytest.raises(SpatialInputError) as error:
        read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326)
    assert error.value.code == "missing_id"
    assert error.value.issues[0]["field"] == "id"


def test_csv_literal_na_is_valid_string_id_while_other_columns_parse_normally(tmp_path):
    from crazy_buffer import read_points_csv

    path = tmp_path / "points.csv"
    path.write_text("id,x,y,value\nNA,116.4,39.9,\n", encoding="utf-8")
    result = read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326)
    assert result["id"].tolist() == ["NA"]
    assert result["value"].isna().all()


@pytest.mark.parametrize("coordinate_system", ["GCJ-02", "BD-09"])
def test_csv_rejects_declared_offset_system(tmp_path, coordinate_system):
    from crazy_buffer import read_points_csv, SpatialInputError

    path = tmp_path / "points.csv"
    path.write_text("id,x,y\na,116.4,39.9\n", encoding="utf-8")
    with pytest.raises(SpatialInputError) as error:
        read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326, coordinate_system=coordinate_system)
    assert error.value.code == "unsupported_coordinate_system"


def test_csv_missing_coordinate_column_locatable(tmp_path):
    from crazy_buffer import read_points_csv, SpatialInputError

    path = tmp_path / "points.csv"
    path.write_text("id,x\na,116.4\n", encoding="utf-8")
    with pytest.raises(SpatialInputError) as error:
        read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326)
    assert error.value.code == "missing_field"
    assert error.value.issues[0]["field"] == "y"


@pytest.mark.parametrize("value", ["", "abc", "inf"])
def test_csv_rejects_missing_nonnumeric_or_nonfinite_coordinates(tmp_path, value):
    from crazy_buffer import read_points_csv, SpatialInputError

    path = tmp_path / "points.csv"
    path.write_text(f"id,x,y\na,{value},39.9\n", encoding="utf-8")
    with pytest.raises(SpatialInputError) as error:
        read_points_csv(path, id_column="id", x_column="x", y_column="y", crs=4326)
    assert error.value.code == "invalid_coordinate"
    assert error.value.issues[0]["id"] == "a"
    assert error.value.issues[0]["field"] == "x"


def test_geopackage_reads_named_layer_and_preserves_id(tmp_path, metric_points):
    from crazy_buffer import read_geopackage

    path = tmp_path / "layers.gpkg"
    metric_points.to_file(path, layer="selected", driver="GPKG")
    result = read_geopackage(path, layer="selected", id_column="id")
    assert result["id"].tolist() == ["a", "b"]
    assert result.crs.to_epsg() == 32650


def test_geopackage_missing_layer_is_locatable(tmp_path, metric_points):
    from crazy_buffer import read_geopackage, SpatialInputError

    path = tmp_path / "layers.gpkg"
    metric_points.to_file(path, layer="existing", driver="GPKG")
    with pytest.raises(SpatialInputError) as error:
        read_geopackage(path, layer="missing", id_column="id")
    assert error.value.code == "missing_layer"
    assert error.value.issues[0]["layer"] == "missing"


def test_geopackage_missing_id_field_is_locatable(tmp_path, metric_points):
    from crazy_buffer import read_geopackage, SpatialInputError

    path = tmp_path / "layers.gpkg"
    metric_points.to_file(path, layer="selected", driver="GPKG")
    with pytest.raises(SpatialInputError) as error:
        read_geopackage(path, layer="selected", id_column="missing")
    assert error.value.code == "missing_field"
    assert error.value.issues[0]["field"] == "missing"
