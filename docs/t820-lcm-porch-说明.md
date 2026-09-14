# T820 LCM Porch / MIPI CLK 计算表（对照说明）

这份文档记录 `t820-lcm-porch.xlsx`（工作表「MIPI CLK计算表」）的原始内容，
以及它是怎么落到 `bsp_tools/timing.py` 里的。**改公式前先看这里**。

## 原始表格

| 单元格 | 内容 | 说明 |
| --- | --- | --- |
| B1 / B2 / B3 | 40 / 40 / 20 | `.hfp` / `.hbp` / `.hsync` |
| B5 / B6 / B7 | 62 / 12 / 8 | `.vfp` / `.vbp` / `.vsync` |
| B9 / B10 | 1200 / 1920 | `.width` / `.height` |
| B12 / B13 | 60 / 4 | `.fps` / `.lan_number` |
| B15 | 384000000 | `SPRDFB_DPI_CLOCK_SRC`（T820 的 DPI 时钟源） |

| 单元格 | 公式 | 值 | 含义 |
| --- | --- | --- | --- |
| F4 | `=(B1+B2+B3+B9)*(B5+B6+B7+B10)*B12` | 156156000 | **Dpi_need_clk**：屏体需求的像素时钟 |
| H2 | `=F4/2` | 78078000 | 半个像素时钟（判据用） |
| G5 | `=INT(B15/F4)` | 2 | 时钟源能装下几个需求时钟（整数商） |
| H3 | `=B15-G5*F4` | 71688000 | 按整数商分频后的余数 |
| F5 | `=IF(H2>H3,G5,G5+1)` | 2 | **最终分频比**：余数 < 半个 pclk 就用商，否则商 +1 |
| H5 | `=B15/F4` | 2.459 | 精确倍数（未取整） |
| H6 | `=B15/F5/(B1+B2+B3+B9)/(B5+B6+B7+B10)` | 73.772 | **实际帧率** |
| F6 | `=INT(H6)` | 73 | 实际帧率取整 |
| H11 | `=(B15/F5)*3*8/0.9/B13` | 1280000000 | **每 lane 需求速率**（bps） |
| F11 | `=INT(H11/1000000)` | 1280 | 同上，单位 Mbps |

判定式（G11 的说明文字）：

```
(DPI_CLK_SRC / DIVIDOR) × 3 × 8bit  <  phy_feq × lane_num × 0.9
```

也就是：`实际 pclk × 24bpp < PHY 速率 × lane 数 × 0.9`。

## 落到代码里的映射（`bsp_tools/timing.py`）

| 表格 | 代码 |
| --- | --- |
| F4 `Dpi_need_clk` | `Timing.pclk_hz` |
| F5 分频比 | `Timing.divisor`（`auto_divisor()` 实现 IF 逻辑，`dpi_divisor` 非 0 时手动优先） |
| H6 实际帧率 | `Timing.actual_fps` |
| H11 每 lane 需求 | `Timing.per_lane_required_bps`（`DSI_EFFICIENCY = 0.9`） |
| G11 判定式 | `Timing.dphy_verdict()` / `per_lane_tone()` |
| B15 时钟源 | `Timing.dpi_source` |

## 几处刻意的差异（都是为健壮性加的）

1. **分频比不会为 0**。表格的 `IF` 在 `时钟源 < 需求` 时（`INT` 得 0）会算出 0 分频，
   实际会除零。代码里夹到 1，并在说明文字里提示「实际帧率达不到需求」。
2. **bpp 不写死 24**。表格用 `3×8`（即 RGB888），代码走 `Timing.bpp`，
   RGB666 / RGB565 / DSC 压缩都能算。
3. **手动分频可覆盖**。表格只有自动；界面上可以手动指定（调试时固定某个分频比看结果）。

## 回归

`devtools/check_timing.py` 的 `[1b]` 段用表格这一组输入逐格对数：
`156156000 / 分频 2 / 余数 71688000 / 实际 pclk 192000000 / 实际帧率 73 / 每 lane 1280000000`。
改公式后这一节必须仍然全绿。
