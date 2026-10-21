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
    assert app.expander[0].label == '质检与运行记录'
    assert app.expander[0].proto.expanded is False
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
