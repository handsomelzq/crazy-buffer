from pathlib import Path
import pytest
pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'src/crazy_buffer/gui/app.py'


@pytest.mark.parametrize('task', ['buffer', 'nearest', 'network'])
def test_demo_run_and_invalidate(task):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.selectbox[0].select(task).run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert 'frozen' in app.session_state
    quality = next(item for item in app.expander if item.label == '质检与运行记录')
    assert quality.proto.expanded is False
    app.text_input[0].set_value('EPSG:3857').run()
    assert 'frozen' not in app.session_state
    app.button[0].click().run()
    assert app.error
    assert 'frozen' not in app.session_state


def test_negative_threshold():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.selectbox[0].select('network').run()
    app.number_input[0].set_value(-1).run()
    app.button[0].click().run()
    assert app.error
    assert 'frozen' not in app.session_state


def test_task_switch_and_threshold_invalidate():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.button[0].click().run()
    assert 'frozen' in app.session_state
    app.selectbox[0].select('network').run()
    assert 'frozen' not in app.session_state
    app.button[0].click().run()
    assert 'frozen' in app.session_state
    app.number_input[0].set_value(50.).run()
    assert 'frozen' not in app.session_state


def test_invalid_analysis_crs():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.text_input[0].set_value('invalid-crs').run()
    app.button[0].click().run()
    assert not app.exception
    assert app.error
    assert 'frozen' not in app.session_state


def test_nonspatial_upload_clears_previous_result(tmp_path, monkeypatch):
    import pandas as pd
    import pyogrio
    import streamlit
    path = tmp_path / 'attributes.gpkg'
    pyogrio.write_dataframe(pd.DataFrame({'id': ['001']}), path, layer='attributes', driver='GPKG')
    class Upload:
        name = 'private-name.gpkg'
        def getvalue(self):
            return path.read_bytes()
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.button[0].click().run()
    assert 'frozen' in app.session_state
    monkeypatch.setattr(streamlit, 'file_uploader', lambda *args, **kwargs: Upload())
    app.radio[0].set_value('上传数据').run()
    assert not app.exception
    assert app.error
    assert '没有空间图层' in app.error[0].value
    assert 'frozen' not in app.session_state
    assert app.button[0].disabled


def test_statistic_id_overlap_explained():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.selectbox[-1].select('id').run()
    app.button[0].click().run()
    assert not app.exception
    assert '独立的数值字段' in app.error[0].value
    assert 'frozen' not in app.session_state


def test_display_controls_do_not_invalidate_analysis():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.button[0].click().run()
    original = app.session_state['frozen']['csv']
    for key in ['basemap', 'visible_sources', 'show_buffer']:
        app.checkbox(key=key).uncheck().run()
        assert not app.exception
        assert app.session_state['frozen']['csv'] == original
    app.number_input(key='radius_合成示例').set_value(100.).run()
    assert 'frozen' not in app.session_state


def test_uploaded_lon_lat_auto_projection_and_preview(monkeypatch):
    import streamlit
    class Upload:
        name = 'sample.csv'
        def getvalue(self):
            return b'id,lon,lat,value\n001,116.4,39.9,10\n002,116.401,39.901,20\n'
    monkeypatch.setattr(streamlit, 'file_uploader', lambda *args, **kwargs: Upload())
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.radio(key='mode').set_value('上传数据').run()
    assert not app.exception
    assert not app.error
    assert app.selectbox(key='x_sources').value == 'lon'
    assert app.selectbox(key='y_sources').value == 'lat'
    projection = next(t for t in app.text_input if t.label == '计算投影（米制 CRS）')
    assert projection.value == 'EPSG:32650'
    app.button[0].click().run()
    assert not app.error
    assert app.session_state['frozen']['result']['mean_value'].tolist() == [15., 15.]
