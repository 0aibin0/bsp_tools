"""亮度表（screenBrightnessMap）的解析、校验与生成。

这块规则是踩出来的，**不要放宽**：

1. `<value>` 与 `<nits>` 都必须**非递减**。只要有一处递减，
   `DisplayDeviceConfig.loadBrightnessMap` 就会丢弃整张表 →
   `getBrightnessFromBacklight` 取不到值直接 NPE → `system_server`
   （android.display 进程）崩溃重启，机器进不了 launcher。
2. 平台 schema **不支持** `highBrightnessMode` 内嵌 `screenBrightnessMap`
   （写进去会被静默跳过），所以 HBM 区间必须并进**顶层表**。
3. `transitionPoint` = HBM **off** 时的亮度上限，也就是高亮度模式的起点，
   等于最后一个非 HBM 点的 `<value>`。
4. `<value>` 是 HAL backlight 0..1，等于 10bit DBV / 1023。

输入格式（一行一个点，`HBM` 可省略）：

    0.000000 1.000000
    0.200000 12.000000
    0.800000 800.000000      <- HBM 起点
    1.000000 1200.000000 HBM

本模块是纯函数，不依赖 Qt，方便单独测（见 devtools/check_brightness_map.py）。
"""

#: `<value>` 满量程对应的 DBV（10bit）
DBV_MAX = 1023


def value_to_dbv(value):
    """HAL value(0..1) → 10bit DBV 节点值。"""
    return int(round(float(value) * DBV_MAX))


def dbv_to_value(dbv):
    """10bit DBV 节点值 → HAL value(0..1)。"""
    return float(dbv) / DBV_MAX


def parse_points(text):
    """解析「value nits [HBM]」清单。

    返回 (points, problems)。points 里每项是
    {"value": float, "nits": float, "hbm": bool, "line": 行号}。
    认 `#` / `//` 注释、逗号或空格分隔、`HBM` 标记。
    """
    points = []
    problems = []
    for lineno, raw in enumerate((text or "").splitlines(), 1):
        line = raw.split("#")[0]
        line = line.split("//")[0].strip()
        if not line:
            continue
        tokens = line.replace(",", " ").replace("\t", " ").split()
        hbm = False
        if tokens and tokens[-1].lower() in ("hbm", "hb", "high"):
            hbm = True
            tokens = tokens[:-1]
        if len(tokens) < 2:
            problems.append(
                "第 {} 行只有 {} 个数字，需要「value nits」".format(
                    lineno, len(tokens)))
            continue
        try:
            value = float(tokens[0])
            nits = float(tokens[1])
        except ValueError:
            problems.append("第 {} 行不是数字：{}".format(lineno, line))
            continue
        points.append({"value": value, "nits": nits,
                       "hbm": hbm, "line": lineno})
    return points, problems


def validate_points(points):
    """校验采样点，返回问题列表（空列表 = 可以拿去生成 XML）。"""
    problems = []
    if len(points) < 2:
        problems.append("至少要 2 个采样点（含最暗和最亮）")

    for index, point in enumerate(points, 1):
        if not 0.0 <= point["value"] <= 1.0:
            problems.append(
                "第 {} 个点 value={} 超出 0..1（value 是 HAL backlight）".format(
                    index, point["value"]))
        if point["nits"] < 0:
            problems.append("第 {} 个点 nits 为负".format(index))

    for index in range(1, len(points)):
        prev, cur = points[index - 1], points[index]
        if cur["value"] < prev["value"]:
            problems.append(
                "第 {} 个点 value {} 小于上一个 {}——value 必须非递减，"
                "否则整张表会被丢弃".format(
                    index + 1, cur["value"], prev["value"]))
        if cur["nits"] < prev["nits"]:
            problems.append(
                "第 {} 个点 nits {} 小于上一个 {}——nits 必须非递减".format(
                    index + 1, cur["nits"], prev["nits"]))
        if cur["value"] == prev["value"] and cur["nits"] != prev["nits"]:
            problems.append(
                "第 {} 与第 {} 个点 value 都是 {} 但 nits 不同，含义含糊".format(
                    index, index + 1, cur["value"]))

    flags = [point["hbm"] for point in points]
    if any(flags):
        first_hbm = flags.index(True)
        if not all(flags[first_hbm:]):
            problems.append("HBM 点必须连续且集中在末尾（顶层表才是有效写法）")
        if first_hbm == 0:
            problems.append(
                "全是 HBM 点：缺少 HBM off 的区间，算不出 transitionPoint")
    return problems


def transition_point(points):
    """transitionPoint = 最后一个**非 HBM** 点的 value（HBM off 时的上限）。"""
    values = [point["value"] for point in points if not point["hbm"]]
    return values[-1] if values else None


def to_xml(points, indent="    "):
    """生成 `<screenBrightnessMap>` 片段（可直接贴进 display_id_*.xml）。"""
    lines = ["<screenBrightnessMap>"]
    for point in points:
        lines.append(indent + "<point>")
        lines.append(indent * 2 + "<value>{:.6f}</value>".format(point["value"]))
        lines.append(indent * 2 + "<nits>{:.6f}</nits>".format(point["nits"]))
        lines.append(indent + "</point>")
    lines.append("</screenBrightnessMap>")
    return "\n".join(lines)


def summary(points):
    """一句话摘要：点数 / nit 区间 / transitionPoint / HBM 点数。"""
    if not points:
        return "没有采样点。"
    values = [point["value"] for point in points]
    nits = [point["nits"] for point in points]
    hbm_count = sum(1 for point in points if point["hbm"])
    text = "{} 个点 · value {:.3f}..{:.3f} · nits {:.1f}..{:.1f}".format(
        len(points), min(values), max(values), min(nits), max(nits))
    tp = transition_point(points)
    if tp is not None:
        text += " · transitionPoint {:.3f}（节点 {}）".format(
            tp, value_to_dbv(tp))
    if hbm_count:
        text += " · HBM {} 个点".format(hbm_count)
    return text
