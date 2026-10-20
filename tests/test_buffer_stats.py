import pandas as pd
from pandas.testing import assert_frame_equal
from crazy_buffer import buffer_stats, neighbors_within, summarize_neighbors
from test_aggregate import fixture_layers


def test_recipe_batches_and_immutable():
    s,t,_=fixture_layers(); s.index=[2,2,8]; t.index=[7]*5
    before_s,before_t=s.copy(deep=True),t.copy(deep=True)
    kwargs=dict(source_id='sid',target_id='tid',radius_m=10,value_column='price')
    links=neighbors_within(s,t,source_id='sid',target_id='tid',radius_m=10)
    expected=summarize_neighbors(links,sources=s,targets=t,**kwargs)
    for size in (1,256): assert_frame_equal(buffer_stats(s,t,**kwargs,batch_size=size),expected)
    assert_frame_equal(s,before_s); assert_frame_equal(t,before_t)


def test_empty_targets():
    s,t,_=fixture_layers()
    result=buffer_stats(s,t.iloc[:0],source_id='sid',target_id='tid',radius_m=10,value_column='price')
    assert result.source_id.tolist()==s.sid.tolist()
    assert result.status.tolist()==['no_matches']*3
    assert result.n_matches.tolist()==[0]*3


def test_value_lookup_prepared_once_and_report(monkeypatch):
    import importlib
    module=importlib.import_module('crazy_buffer.recipes.buffer_stats')
    from crazy_buffer import RunReport
    original=module._prepare_values
    calls=[]
    def tracked(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(module,'_prepare_values',tracked)
    s,t,_=fixture_layers(); report=RunReport()
    module.buffer_stats(s,t,source_id='sid',target_id='tid',radius_m=10,value_column='price',batch_size=1,report=report)
    assert len(calls)==1
    assert report.steps[-1]['name']=='buffer_stats'


def test_extreme_finite_mean_recipe():
    import pytest
    for values,expected in [([1e308,1e308],1e308),([-1e308,-1e308],-1e308),([1e308,-1e308],0.),([-1e308,1e308],0.)]:
        s,t,_=fixture_layers()
        t=t.iloc[:2].copy()
        t.loc[:,'price']=values
        result=buffer_stats(s,t,source_id='sid',target_id='tid',radius_m=10,value_column='price',batch_size=1)
        assert result.iloc[0].mean_value==pytest.approx(expected)
        assert result.iloc[0].status=='ok'
