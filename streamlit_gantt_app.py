import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from dateutil import parser
import streamlit.components.v1 as components

_gantt = components.declare_component(
    "streamlit_gantt",
    path=r"F:\work\codes\task\streamlit-gantt\streamlit_gantt\frontend\build",
)

def st_gantt(tasks=None, height=500, key=None):
    return _gantt(tasks=tasks, height=height, key=key, default=None)

# ===================== streamlit-gantt 基准日期 =====================
# 该组件内部以 2026-04-01 为基准日，start 字段是天偏移量（整数）
BASE_DATE = datetime(2026, 4, 1)

# 优先级配色（组件内置 8 色调色板）
priority_color_map = {
    "高": "#f87171",  # Red
    "中": "#f59e0b",  # Amber
    "低": "#10b981",  # Emerald
}


# ===================== 日期 <-> 偏移量 转换 =====================

def date_to_offset(dt):
    """将 datetime 转为相对于 BASE_DATE(2026-04-01) 的天数偏移量"""
    if isinstance(dt, datetime):
        delta = dt - BASE_DATE
    else:
        dt = datetime.combine(dt, datetime.min.time())
        delta = dt - BASE_DATE
    return delta.days


def offset_to_date(offset):
    """将偏移量转回 datetime"""
    return BASE_DATE + timedelta(days=int(offset))


def date_range_to_params(start_dt, end_dt):
    """将起止 datetime 转为 (start_offset, duration_days)"""
    start_offset = date_to_offset(start_dt)
    delta = end_dt - start_dt
    duration_days = max(1, int(delta.total_seconds() / 86400))
    return start_offset, duration_days


# ===================== AI自动识别解析函数 =====================

def parse_task_text(raw_text):
    """
    输入多行原始任务文本，自动识别任务名、开始时间、结束时间、优先级
    返回DataFrame，字段: Task, Start, End, Priority
    """
    lines = raw_text.strip().splitlines()
    task_list = []
    print(lines)
    time_pattern = re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}")
    priority_pattern = re.compile(r"([高低中])\s*(优先级|优先)?")

    for line in lines:
        line = line.strip()
        print(f"解析行：{line}")
        if not line:
            continue

        time_matches = time_pattern.findall(line)
        print(time_matches)
        if len(time_matches) < 2:
            st.warning(f"该行缺少起止两个时间，跳过：{line}")
            continue

        start_str = time_matches[0]+" 00:00"
        end_str = time_matches[1]+" 01:00"
        print(f"识别时间：{start_str} ~ {end_str}")

        prio_match = priority_pattern.search(line)
        if prio_match:
            priority = prio_match.group(1)
        else:
            st.warning(f"该行未识别优先级，默认【低】：{line}")
            priority = "低"

        task_name = line
        task_name = time_pattern.sub("", task_name)
        task_name = priority_pattern.sub("", task_name)
        task_name = re.sub(r"[:：，,~～\-至]", " ", task_name)
        task_name = re.sub(r"\s+", " ", task_name).strip()
        if not task_name:
            st.warning(f"任务名称识别为空，跳过：{line}")
            continue

        try:
            start_dt = parser.parse(start_str)
            end_dt = parser.parse(end_str)
            task_list.append(
                {
                    "Task": task_name.strip(),
                    "Start": start_dt,
                    "End": end_dt,
                    "Priority": priority,
                }
            )
        except Exception as e:
            st.warning(f"时间解析失败：{line}, err:{e}")

    df = pd.DataFrame(task_list)
    if not df.empty:
        df = df.sort_values("Start", ascending=True).reset_index(drop=True)
    return df


# ===================== 内部DataFrame <-> streamlit-gantt 格式转换 =====================

def df_to_gantt_tasks(df):
    """把内部任务DataFrame转为 streamlit-gantt 需要的 list[dict]"""
    if df.empty:
        return []

    tasks = []
    for idx, row in df.iterrows():
        start_dt = row["Start"]
        end_dt = row["End"]
        start_offset, duration = date_range_to_params(start_dt, end_dt)
        color = priority_color_map.get(row.get("Priority", "低"), "#6366f1")

        tasks.append(
            {
                "id": int(idx),
                "name": str(row["Task"]),
                "start": start_offset,
                "duration": int(duration),
                "progress": 0,
                "color": color,
                "deps": [],
                "milestone": False,
            }
        )
    return tasks


def gantt_result_to_df(result):
    """把 streamlit-gantt 返回的 dict 转回内部任务DataFrame"""
    if not result or "tasks" not in result or not result["tasks"]:
        return pd.DataFrame()

    task_list = []
    for t in result["tasks"]:
        start_offset = t.get("start", 0)
        duration = t.get("duration", 1)
        start_dt = offset_to_date(start_offset)
        end_dt = start_dt + timedelta(days=int(duration))

        # 通过颜色反查优先级
        color = t.get("color", "")
        priority = "低"
        for p, c in priority_color_map.items():
            if c == color:
                priority = p
                break

        task_list.append(
            {
                "Task": t.get("name", ""),
                "Start": start_dt,
                "End": end_dt,
                "Priority": priority,
            }
        )

    df = pd.DataFrame(task_list)
    if not df.empty:
        df = df.sort_values("Start", ascending=True).reset_index(drop=True)
    return df


# ===================== 会话状态初始化 =====================

if "gantt_tasks" not in st.session_state:
    st.session_state["gantt_tasks"] = pd.DataFrame()

if "gantt_tasks_raw" not in st.session_state:
    st.session_state["gantt_tasks_raw"] = []

st.set_page_config(page_title="任务甘特图", layout="wide")

st.title("任务排序 + 甘特图")
st.markdown(
    """
输入任务文本，解析后生成甘特图，可直接拖拽调整任务时间。

示例写法：

- 任务 A：2026-10-10 08:00 ~ 2026-10-10 12:00，高优先级
- 任务 B 2026-10-10 13:00至2026-10-10 17:00 中
- 任务C，低优先级，时间：2026-10-11 09:00 - 2026-10-11 11:00
"""
)

input_text = st.text_area("输入任务清单", height=220)

if st.button("解析并生成甘特图"):
    df_tasks = parse_task_text(input_text)
    if df_tasks.empty:
        st.error("未识别到有效任务，请检查格式！")
    else:
        st.session_state["gantt_tasks"] = df_tasks
        gantt_tasks = df_to_gantt_tasks(df_tasks)
        st.session_state["gantt_tasks_raw"] = gantt_tasks
        st.success("文本解析完成，甘特图将重新渲染！")

# ===================== 可编辑任务表格 =====================

st.subheader("原始任务清单")
# 可编辑

if not st.session_state["gantt_tasks"].empty:
    edit_df = st.session_state["gantt_tasks"].copy()
    edit_df.columns = ["任务名称", "开始时间", "结束时间", "优先级"]

    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "优先级": st.column_config.SelectboxColumn(
                "优先级", options=["高", "中", "低"], required=True
            ),
            "开始时间": st.column_config.DatetimeColumn(
                "开始时间", format="YYYY-MM-DD HH:mm"
            ),
            "结束时间": st.column_config.DatetimeColumn(
                "结束时间", format="YYYY-MM-DD HH:mm"
            ),
        },
        key="task_editor",
    )

    if st.button("应用表格修改并刷新甘特图"):
        try:
            edited_df.columns = ["Task", "Start", "End", "Priority"]
            edited_df["Start"] = pd.to_datetime(edited_df["Start"])
            edited_df["End"] = pd.to_datetime(edited_df["End"])

            if (edited_df["End"] < edited_df["Start"]).any():
                st.error("存在任务结束时间早于开始时间，请检查！")
            else:
                edited_df = edited_df.sort_values("Start").reset_index(drop=True)
                st.session_state["gantt_tasks"] = edited_df
                gantt_tasks = df_to_gantt_tasks(edited_df)
                st.session_state["gantt_tasks_raw"] = gantt_tasks
                st.success("表格修改生效，甘特图已刷新！")
        except Exception as e:
            st.error(f"表格数据解析失败：{e}")

# ===================== 渲染 streamlit-gantt 甘特图 =====================

st.subheader("甘特图")
# 可拖拽
# 导入组件
if st.session_state.get("gantt_tasks_raw"):
    # 获取当前任务数据（list[dict] 格式）
    current_tasks = st.session_state.get("gantt_tasks_raw", [])

    # 调用组件
    # tasks: 初始任务列表（None=演示数据, []=空白, list=自定义）
    # height: 组件高度(px)
    # key: 组件唯一标识
    result = st_gantt(tasks=current_tasks if current_tasks else None, height=900, key="gantt")

    # 处理拖拽返回结果
    if result and isinstance(result, dict) and "tasks" in result:
        df_updated = gantt_result_to_df(result)

        if not df_updated.empty:
            # 更新会话状态，实现双向同步
            st.session_state["gantt_tasks"] = df_updated
            st.session_state["gantt_tasks_raw"] = df_to_gantt_tasks(df_updated)
            st.success("甘特图拖拽修改已同步到任务表格！")

            # 展示更新后的数据
            st.write("**拖拽更新后的任务数据：**")
            st.dataframe(df_updated, use_container_width=True)
