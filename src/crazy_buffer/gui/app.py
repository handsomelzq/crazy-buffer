"""Local spatial workbench: layers, map, and a small parameter panel."""
import hashlib
import json
from pathlib import Path

import streamlit as st

from crazy_buffer.gui.map_view import build_map
from crazy_buffer.gui.service import demo_inputs, inspect_upload, load_upload, freeze_run

st.set_page_config(page_title='Crazy Buffer · 空间分析工作台', layout='wide')
st.markdown(
    f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)
TASKS = {
    'buffer': '缓冲区统计',
    'facilities': '周边设施',
    'landuse': '用地构成',
    'nearest': '最近直线距离',
    'network': '路网步行距离',
}
LABELS = {
    'sources': '研究对象',
    'targets': '目标点',
    'edges': '步行道路',
    'land_use': '用地分类',
}
COLORS = {
    'sources': '🟢', 'targets': '🟠', 'edges': '🔵', 'land_use': '🟡',
}
TASK_ROLES = {
    'buffer': ['sources', 'targets'],
    'nearest': ['sources', 'targets'],
    'network': ['sources', 'targets', 'edges'],
    'facilities': ['sources', 'targets'],
    'landuse': ['sources', 'land_use'],
}
brand, task_area = st.columns([3, 1.4], vertical_alignment='center')
with brand:
    st.markdown('<div class="brand"><span class="brand-mark">⊕</span><span>CRAZY BUFFER'
                '<small>空间分析工作台 / LOCAL WORKSPACE</small></span></div>', unsafe_allow_html=True)
with task_area:
    task = st.selectbox('分析工具', list(TASKS), format_func=TASKS.get, key='task')
left, center, right = st.columns([1.05, 3.1, 1.25], gap='medium')
params = {'task': task}
inputs = {}
fingerprint_parts = []
ready = True
roles = TASK_ROLES[task]
visible_roles = []
with left:
    st.markdown('<div class="panel-label">01 / 图层与数据</div>', unsafe_allow_html=True)
    mode = st.radio('数据来源', ['合成示例', '上传数据'], horizontal=True, key='mode')
    if mode == '合成示例':
        inputs = demo_inputs()
        # Place the synthetic metre grid near Beijing, preserving all distances.
        for frame in inputs.values():
            frame.geometry = frame.geometry.translate(xoff=448000, yoff=4418000)
        st.caption('虚构示例，放置于北京附近以演示地图。不是当地真实对象。')
    else:
        st.caption('CSV 点表 / GPKG 图层 · 每文件 ≤ 20 MB')
    for role in roles:
        with st.container(border=True):
            st.markdown(f'**{COLORS[role]} {LABELS[role]}**')
            if mode == '上传数据':
                upload = st.file_uploader(f'{LABELS[role]}文件', type=['gpkg'] if role in {'edges', 'land_use'} else ['csv', 'gpkg'],
                                          key=f'upload_{role}', label_visibility='collapsed')
                if upload is None:
                    ready = False
                    continue
                data = upload.getvalue()
                kind = 'csv' if upload.name.lower().endswith('.csv') else 'gpkg'
                fingerprint_parts.append((role, hashlib.sha256(data).hexdigest()))
                try:
                    metadata = inspect_upload(data, kind)
                    if kind == 'gpkg':
                        layers = metadata['layers']
                        layer = layers[0] if len(layers) == 1 else st.selectbox('选择图层', layers, key=f'layer_{role}')
                        fingerprint_parts.append(layer)
                        inputs[role] = load_upload(data, kind=kind, role=role, layer=layer)
                    else:
                        columns = metadata['columns']
                        if not columns:
                            raise ValueError('CSV 缺少字段。')
                        def field_index(candidates, fallback):
                            return next((i for i, c in enumerate(columns) if c.lower() in candidates), min(fallback, len(columns)-1))
                        with st.expander('确认坐标字段', expanded=True):
                            x = st.selectbox('经度 / X', columns, index=field_index({'lon', 'lng', 'longitude', 'x', '经度'}, 0), key=f'x_{role}')
                            y = st.selectbox('纬度 / Y', columns, index=field_index({'lat', 'latitude', 'y', '纬度'}, 1), key=f'y_{role}')
                            crs = st.text_input('原始坐标系', value='EPSG:4326', key=f'crs_{role}', help='仅适用于原始 WGS84 经纬度；其他坐标请填写真实 CRS。')
                        if x == y:
                            raise ValueError('经度和纬度必须选择不同字段。')
                        fingerprint_parts.extend([x, y, crs])
                        inputs[role] = load_upload(data, kind=kind, role=role, x=x, y=y, crs=crs)
                except Exception as exc:
                    inputs.pop(role, None)
                    st.session_state.pop('frozen', None)
                    st.error(f'{LABELS[role]}读取失败：{exc}')
                    ready = False
            if role in inputs:
                frame = inputs[role]
                fields = [c for c in frame.columns if c != frame.geometry.name]
                st.caption(f'{len(frame):,} 个对象 · {frame.crs.to_string()}')
                if st.checkbox('在地图上显示', value=True, key=f'visible_{role}'):
                    visible_roles.append(role)
                with st.expander('字段与属性'):
                    if fields:
                        params[role + '_id'] = st.selectbox('唯一标识字段', fields, index=fields.index('id') if 'id' in fields else 0, key=f'id_{role}')
                    else:
                        st.error('数据需要一个唯一标识字段。')
                        ready = False
                    st.dataframe(frame.drop(columns=frame.geometry.name).head(5), hide_index=True)
    st.caption('文件在本机处理。地图仅展示，不编辑原始数据。')
with right:
    st.markdown('<div class="panel-label">02 / 分析设置</div>', unsafe_allow_html=True)
    st.subheader(TASKS[task])
    if task == 'buffer':
        st.caption('为每个研究对象划定范围，计算其中目标点的数值均值。')
        params['radius_m'] = st.number_input('缓冲距离（米）', value=50.0 if mode == '合成示例' else 1500.0, step=10.0, key=f'radius_{mode}')
        if 'targets' in inputs:
            fields = [c for c in inputs['targets'].columns if c != inputs['targets'].geometry.name]
            if fields:
                params['value_column'] = st.selectbox('要统计的数值', fields, index=fields.index('value') if 'value' in fields else 0, key='value_column')
            else:
                ready = False
        st.caption('按目标样本等权平均；面对象以完整边界向外缓冲。')
    elif task == 'nearest':
        st.caption('为每个研究点寻找直线距离最近的目标点，输出米制距离。')
    elif task == 'network':
        st.caption('先接入道路，再沿路网寻找最近可达的目标点。')
        params['max_snap_distance_m'] = st.number_input('最大接入距离（米）', value=100.0, step=10.0, key='max_snap')
        st.caption('道路须已有正确拓扑。线内部交叉不会自动连通。')
    elif task == 'facilities':
        st.caption('统计每个研究对象周边各类设施的数量、密度与多样性。')
        params['radius_m'] = st.number_input(
            '搜索距离（米）', value=50.0 if mode == '合成示例' else 1500.0,
            step=10.0, key=f'facility_radius_{mode}',
        )
        if 'targets' in inputs:
            fields = [c for c in inputs['targets'].columns if c != inputs['targets'].geometry.name]
            preferred = fields.index('type') if 'type' in fields else 0
            params['category_column'] = st.selectbox(
                '设施类别字段', fields, index=preferred, key='facility_category',
            )
        st.caption('密度以完整缓冲面积计；混合度按研究范围内出现的类别计算。')
    else:
        st.caption('统计研究单元内各类用地的面积、占比与功能混合度。')
        source_types = (
            set(inputs['sources'].geometry.geom_type)
            if 'sources' in inputs else set()
        )
        self_supported = bool(source_types) and source_types <= {'Polygon', 'MultiPolygon'}
        scope_options = ['向外缓冲'] + (['研究对象自身'] if self_supported else [])
        scope = st.radio(
            '统计范围', scope_options, horizontal=True,
            key=f'landuse_scope_{mode}',
        )
        params['buffer_sources'] = scope == '向外缓冲'
        if params['buffer_sources']:
            params['radius_m'] = st.number_input(
                '缓冲距离（米）', value=50.0 if mode == '合成示例' else 1500.0,
                step=10.0, key=f'landuse_radius_{mode}',
            )
        if 'land_use' in inputs:
            fields = [c for c in inputs['land_use'].columns if c != inputs['land_use'].geometry.name]
            preferred = fields.index('use') if 'use' in fields else 0
            params['category_column'] = st.selectbox(
                '用地类别字段', fields, index=preferred, key='land_use_category',
            )
        st.caption('占比以分析范围面积为分母；覆盖率提示分类数据缺口。')
        if not self_supported:
            st.caption('研究对象为点时使用向外缓冲；上传规则面后可直接按自身范围统计。')
    default_crs = 'EPSG:32650' if mode == '合成示例' else ''
    if mode != '合成示例' and 'sources' in inputs and len(inputs['sources']):
        try:
            suggestion = inputs['sources'].estimate_utm_crs()
            if suggestion:
                default_crs = suggestion.to_string()
        except Exception:
            pass
    with st.expander('进阶设置', expanded=False):
        params['analysis_crs'] = st.text_input('计算投影（米制 CRS）', value=default_crs,
            key=f"analysis_{mode}_{hashlib.sha256(str(fingerprint_parts).encode()).hexdigest()[:12]}",
            help='依据研究对象位置建议 UTM；跨分区或大范围研究请自行指定适用投影。')
        st.caption('地图转换为 WGS84 显示；距离计算使用这里的米制投影。')
        st.caption('GCJ-02 / BD-09 偏移坐标需先转换，不能仅改 CRS 标签。')
        if task == 'network':
            params['directed'] = st.checkbox('道路按坐标顺序单向通行', value=False, key='directed')
            if 'edges' in inputs:
                columns = ['（不指定）'] + [c for c in inputs['edges'].columns if c != inputs['edges'].geometry.name]
                start = st.selectbox('道路起点节点字段', columns, key='from_node')
                end = st.selectbox('道路终点节点字段', columns, key='to_node')
                params['from_node'] = None if start == columns[0] else start
                params['to_node'] = None if end == columns[0] else end
            st.caption('接入线不判断围墙、入口和步行权限；不可达距离留空。')
    st.caption(f"计算投影：{params['analysis_crs'] or '待指定'}")
    fingerprint = hashlib.sha256(json.dumps([mode, params, fingerprint_parts], sort_keys=True).encode()).hexdigest()
    if st.session_state.get('fingerprint') != fingerprint or not ready:
        st.session_state.pop('frozen', None)
    st.session_state['fingerprint'] = fingerprint
    if st.button('运行分析', disabled=not ready, type='primary', width='stretch'):
        st.session_state.pop('frozen', None)
        try:
            with st.spinner('正在本地计算…'):
                st.session_state['frozen'] = freeze_run(inputs, params)
        except Exception as exc:
            st.error(f'分析失败：{exc}')
    if 'frozen' in st.session_state:
        frozen = st.session_state['frozen']
        st.success('分析完成')
        st.download_button('下载结果 CSV', frozen['csv'], 'results.csv', 'text/csv', width='stretch')
        st.download_button('下载可复现 ZIP', frozen['zip'], 'crazy-buffer-run.zip', 'application/zip', width='stretch')
        st.caption('ZIP 包含输入快照、参数与重放脚本。')
with center:
    st.markdown('<div class="panel-label">研究区 / MAP VIEW</div>', unsafe_allow_html=True)
    controls = st.columns([1, 1, 1.4])
    with controls[0]:
        basemap = st.checkbox('显示底图', value=True, key='basemap')
    with controls[1]:
        buffer_enabled = task in {'buffer', 'facilities', 'landuse'}
        show_buffer = st.checkbox('缓冲预览', value=True, disabled=not buffer_enabled, key='show_buffer')
    with controls[2]:
        st.caption('拖动平移 · 滚轮缩放')
    deck, warnings = build_map({r: inputs[r] for r in roles if r in inputs}, params, visible_roles=visible_roles,
                               show_buffer=show_buffer, basemap=basemap)
    st.pydeck_chart(deck, height=540, key='workspace_map')
    for warning in warnings:
        st.warning(warning)
    st.caption('● 绿色：研究对象　● 陶土色：目标点　● 黄绿：用地分类　━ 蓝灰色：道路　◯ 淡绿：缓冲预览')
    if basemap:
        st.caption('底图 © OpenStreetMap contributors / CARTO · 需联网加载。地图视野会发送给瓦片服务；分析文件不上传。底图不可用时，可关闭底图继续查看数据。')
    if mode == '合成示例':
        st.caption('示例仅演示相对空间关系，地图上的位置不代表真实公园、房屋或道路。')
    if 'frozen' in st.session_state:
        frozen = st.session_state['frozen']
        st.markdown('**分析结果**')
        st.dataframe(frozen['result'], hide_index=True, width='stretch')
        with st.expander('质检与运行记录', expanded=False):
            st.json({'质检问题': frozen['report'].issues, '步骤': frozen['report'].steps})
    else:
        st.caption('准备好图层后，点击右侧「运行分析」。结果将在这里显示。')
