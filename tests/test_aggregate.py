import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point
from crazy_buffer import SpatialInputError, summarize_neighbors


def fixture_layers():
    sources = gpd.GeoDataFrame({'sid':['P1','P2','P3']}, geometry=[Point(0,0),Point(100,0),Point(200,0)], crs=32650)
    targets = gpd.GeoDataFrame({'tid':['a','b','c','d','e'], 'price':[10000,20000,None,30000,None]}, geometry=[Point(0,0)]*5, crs=32650)
    links = pd.DataFrame({'source_id':['P1']*4+['P3'], 'target_id':list('abcde'), 'distance_m':[0.]*5, 'radius_m':[10.]*5})
    return sources, targets, links


def summarize(s,t,l,**kw):
    return summarize_neighbors(l,sources=s,targets=t,source_id='sid',target_id='tid',value_column='price',**kw)


def test_statuses_and_filter():
    s,t,l=fixture_layers()
    result=summarize(s,t,l).set_index('source_id')
    p1,p2,p3=(result.loc[x] for x in s.sid)
    assert (p1.n_matches,p1.n_valid_values,p1.mean_value,p1.status)==(4,3,20000.,'ok')
    assert (p2.n_matches,p2.n_valid_values,p2.status)==(0,0,'no_matches')
    assert (p3.n_matches,p3.n_valid_values,p3.status)==(1,0,'no_valid_values')
    assert pd.isna(p2.mean_value) and pd.isna(p3.mean_value)
    assert summarize(s,t,l.iloc[:1]).iloc[0].mean_value==10000
    t.loc[0,'price']=0
    assert summarize(s,t,l.iloc[:1]).iloc[0].mean_value==0


@pytest.mark.parametrize('value',['100',True,float('inf')])
def test_invalid_values(value):
    s,t,l=fixture_layers(); t['price']=t.price.astype(object); t.loc[0,'price']=value
    with pytest.raises(SpatialInputError): summarize(s,t,l)


@pytest.mark.parametrize('kind',['duplicate','orphan','negative','far','mixed','radius','distance_bool','id_bool'])
def test_invalid_links(kind):
    s,t,l=fixture_layers()
    if kind=='duplicate': l=pd.concat([l,l.iloc[:1]],ignore_index=True)
    if kind=='orphan': l.loc[0,'target_id']='missing'
    if kind=='negative': l.loc[0,'distance_m']=-1
    if kind=='far': l.loc[0,'distance_m']=11
    if kind=='mixed': l.loc[0,'radius_m']=20
    if kind=='radius': l.loc[0,'radius_m']=float('inf')
    if kind=='distance_bool': l['distance_m']=l.distance_m.astype(object); l.loc[0,'distance_m']=True
    if kind=='id_bool': l.loc[0,'source_id']=True
    with pytest.raises(SpatialInputError): summarize(s,t,l)


def test_empty_and_explicit_radius():
    s,t,l=fixture_layers()
    with pytest.raises(SpatialInputError): summarize(s,t,l.iloc[:0])
    with pytest.raises(SpatialInputError): summarize(s,t,l,radius_m=20)
    assert list(summarize(s,t,l.iloc[:0],radius_m=10).status)==['no_matches']*3


@pytest.mark.parametrize('bad',[True,1.0])
def test_integer_relation_id_kind(bad):
    s,t,l=fixture_layers()
    s['sid']=[1,2,3]; t['tid']=[1,2,3,4,5]
    l['source_id']=pd.Series([bad,1,1,1,3],dtype=object)
    l['target_id']=[1,2,3,4,5]
    with pytest.raises(SpatialInputError): summarize(s,t,l)


@pytest.mark.parametrize('values,expected',[
    ([1e308,1e308],1e308),
    ([-1e308,-1e308],-1e308),
    ([1e308,-1e308],0.),
    ([-1e308,1e308],0.),
])
def test_extreme_finite_mean(values,expected):
    s,t,l=fixture_layers()
    t.loc[:1,'price']=values
    result=summarize(s,t,l.iloc[:2])
    assert result.iloc[0].mean_value==pytest.approx(expected)
    assert result.iloc[0].status=='ok'
