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
