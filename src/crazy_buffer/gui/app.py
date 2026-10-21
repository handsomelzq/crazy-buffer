"""Chinese local-only Streamlit interface."""
import hashlib
import json

import streamlit as st
from crazy_buffer.gui.service import demo_inputs, inspect_upload, load_upload, freeze_run

st.set_page_config(page_title='Crazy Buffer 本地空间分析', layout='wide')
st.title('本地空间分析试用')
st.caption('内存型小范围试用 · 文件仅在本机临时处理 · 不下载外部数据')
task = st.selectbox('1. 选择分析', ['buffer', 'nearest', 'network'], format_func=lambda key: {'buffer': '缓冲均值统计', 'nearest': '直线最近点距离', 'network': '估计路网步行距离'}[key])
mode = st.radio('2. 数据来源', ['合成示例', '上传数据'], horizontal=True)
st.info('均值按范围内目标样本等权计算，不是面域平均。坐标必须为已声明 CRS 的原始坐标；GCJ-02 / BD-09 偏移坐标请先在外部合法转换。')
params = {'task': task}
inputs = {}
fingerprint_parts = []
ready = True
roles = ['sources', 'targets'] + (['edges'] if task == 'network' else [])
labels = {'sources': '源对象（点或缓冲统计公园面）', 'targets': '目标点', 'edges': '道路'}
if mode == '合成示例':
    inputs = demo_inputs()
    st.success('当前使用确定性合成米制坐标示例，不是真实北京数据。')
else:
    st.caption('上限：每文件 20 MB；源点 5000、目标点 5000、道路 20000 行。道路仅接受 GPKG LineString。')
    for role in roles:
        upload = st.file_uploader(f'{labels[role]}文件', type=['gpkg'] if role == 'edges' else ['csv', 'gpkg'], key=f'upload_{role}')
        if upload is None:
            ready = False
            continue
        data = upload.getvalue()
        kind = 'csv' if upload.name.lower().endswith('.csv') else 'gpkg'
        fingerprint_parts.append(hashlib.sha256(data).hexdigest())
        try:
            metadata = inspect_upload(data, kind)
            if kind == 'gpkg':
                layer = st.selectbox(f'{labels[role]} GPKG 图层（必选）', metadata['layers'], key=f'layer_{role}')
                fingerprint_parts.append(layer)
                inputs[role] = load_upload(data, kind=kind, role=role, layer=layer)
            else:
                columns = metadata['columns']
                x = st.selectbox(f'{labels[role]} X / 经度字段', columns, key=f'x_{role}')
                y = st.selectbox(f'{labels[role]} Y / 纬度字段', columns, index=min(1, len(columns)-1), key=f'y_{role}')
                crs = st.text_input(f'{labels[role]} 原始 CRS', value='EPSG:4326', key=f'crs_{role}')
                fingerprint_parts.extend([x, y, crs])
                inputs[role] = load_upload(data, kind=kind, role=role, x=x, y=y, crs=crs)
        except Exception as exc:
            inputs.pop(role, None)
            st.session_state.pop('frozen', None)
            st.error(f'{labels[role]}读取失败：{exc}')
            ready = False
params['analysis_crs'] = st.text_input('3. 分析 CRS（本地区域适用的投影米制 CRS）', value='EPSG:32650' if mode == '合成示例' else '', key=f'analysis_{mode}')
st.caption('EPSG:32650 仅为示例默认值；请按实际研究区选择。排除 Web Mercator。')
for role in roles:
    if role not in inputs:
        continue
    frame = inputs[role]
    fields = [column for column in frame.columns if column != frame.geometry.name]
    params[role + '_id'] = st.selectbox(f'{labels[role]}唯一 ID 字段', fields, key=f'id_{role}')
    st.caption(f'{labels[role]}：{len(frame)} 行；原始 CRS：{frame.crs}')
    st.dataframe(frame.drop(columns=frame.geometry.name).head(5))
if task == 'buffer':
    params['radius_m'] = st.number_input('半径（米）', value=50.0, step=10.0)
    if 'targets' in inputs:
        fields = [c for c in inputs['targets'].columns if c != inputs['targets'].geometry.name]
        params['value_column'] = st.selectbox('目标统计值字段', fields, index=fields.index('value') if 'value' in fields else 0)
if task == 'network':
    params['max_snap_distance_m'] = st.number_input('最大接入距离（米）', value=100.0, step=10.0)
    params['directed'] = st.checkbox('沿道路坐标起点到终点单向通行', value=False)
    st.warning('默认双向；仅完全相同端点连接，线内部交叉不连通。显式节点可区分桥面与地面；吸附不判断围墙、入口或真实步行权限。不可达距离保留为空。')
    if 'edges' in inputs:
        columns = ['（不指定）'] + [c for c in inputs['edges'].columns if c != inputs['edges'].geometry.name]
        start = st.selectbox('道路起点节点字段（可选）', columns)
        end = st.selectbox('道路终点节点字段（可选）', columns)
        params['from_node'] = None if start == columns[0] else start
        params['to_node'] = None if end == columns[0] else end
fingerprint = hashlib.sha256(json.dumps([mode, params, fingerprint_parts], sort_keys=True).encode()).hexdigest()
if st.session_state.get('fingerprint') != fingerprint or not ready:
    st.session_state.pop('frozen', None)
st.session_state['fingerprint'] = fingerprint
if st.button('4. 运行分析', disabled=not ready):
    st.session_state.pop('frozen', None)
    try:
        with st.spinner('正在本地计算…'):
            st.session_state['frozen'] = freeze_run(inputs, params)
    except Exception as exc:
        st.error(f'分析失败：{exc}')
        if hasattr(exc, 'issues'):
            st.json(exc.issues)
if 'frozen' in st.session_state:
    frozen = st.session_state['frozen']
    st.subheader('5. 结果与下载')
    st.dataframe(frozen['result'])
    st.download_button('下载结果 CSV', frozen['csv'], 'results.csv', 'text/csv')
    st.download_button('下载可复现 ZIP', frozen['zip'], 'crazy-buffer-run.zip', 'application/zip')
    st.caption(f"质检记录：{len(frozen['report'].issues)} 条问题")
    with st.expander('质检与运行记录', expanded=False):
        st.json({'质检问题': frozen['report'].issues, '步骤': frozen['report'].steps})
