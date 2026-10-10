# 长路线原始任务与规划来源

最终测试入口为 ../extended-clearance-aligned-20261008-01/tasks.json。

固定种子 20261008，第 165 对采样端点通过几何与居中规划检查。筛选没有使用 Jev 表现。select_route.py 保存筛选过程，调用现有 NavMesh、ClearancePlanner 和几何统计；重放筛选时只向 /tmp 写中间结果。

原最短路线在 tasks.json；居中路线在 clearance/tasks.json。初始朝向随后由 prepare_initial_heading.py 对齐。原最短距离用于 SPL。
