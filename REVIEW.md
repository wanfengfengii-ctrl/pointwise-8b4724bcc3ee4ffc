# 澄屿两级复核签报

夜班要核定最终放行且保留指定交接的试板中，有多少完成了复检和见证。工位绕行可能从最终路线中消失，实际经过的重置工位仍会使试板失去复核资格。原有转送、试走与 V1 放行签报见 `README.md`。

## 源修订与到达规则

- `source.intake.receive` 和 `source.corrections.amend` 增加可选关键字参数 `labels=None`，原有位置参数照旧。`labels` 是站名到 `recheck`（复检）、`witness`（见证）或 `reset`（重置）的映射，公开及私有站均可登记。每站至多一个标签，终局不能有标签。接纳时省略为无标签。勘误时未列的站继承确切父修订，列出站名与标签即替换，值为 `None` 即清除。只改标签时可传空的计数替换序列。未知站、非法标签和非法映射报 `source.validation.InvalidCounts`，不新增修订。
- `source.revisions.load_revision` 返回的修订通过 `labels` 提供该版已登记的站标签，旧修订视为空映射。计数及标签一起按修订固定，旧父版仍可按号读取。
- 阶段 `0` 表示未复检，`1` 表示已复检，`2` 表示已完成。起站阶段为 `0`，放到起站本身不触发标签。每次实际转送到站时恰处理一次到达标签，包括返回起站和公开自返。`recheck` 令 `0→1`，`witness` 令 `1→2`，`reset` 令任意阶段变为 `0`，其余情况保持原阶段。放行和拒绝沿用到达终局之前的阶段。

## 固定复核计划

新增 `plans.freeze.freeze_review_plan(source, archive, revision_id)`，从指定已提交源修订发行 V2 固定计划。返回值提供 `plan_id`、`revision_id` 及按 V1 声明序排列的 `stations`。在源库关闭、归档库重开后，`plans.catalog.load_plan(archive, plan_id)` 可按原号恢复计划。冻结使用原有计划编号空间，失败沿用 `FreezeError` 且无新计划，未知计划号仍报 `PlanNotFound`。

V2 的 `row_for(station, phase)` 提供从给定公开站、给定入段阶段继续转送的联合概率映射。键为 `(outcome, next_phase)`，其中 `outcome` 可以是公开站名或现有 `PlanOutcome.RELEASE`、`PlanOutcome.REJECT`、`PlanOutcome.NEVER`。到达公开站的标签效果已计入 `next_phase`，离开该站进行下一段时不得再次处理同一次到达。放行和拒绝的键带终局阶段。`NEVER` 使用单独的 `(PlanOutcome.NEVER, None)`，包括无可观测出边及私有流程永不抵达公开站或终局的质量。合法行给出各公开站和两个终局的三个阶段组合，以及滞留项，值均为非负 `Fraction`，合计为一。即使某个阶段在特定起站请求中不可达，计划也须提供该入段阶段的行。站名与终局枚举沿用 V1 的区分。原始计数、私有站名及私有标签留在源库。

## 断源签发与领取

新增 `analysis.request.publish_review_report(archive, plan_id, start, handoff, *, before_commit=None)`。它只使用指定 V2 计划。起站和有向交接端点沿用 V1 的公开站校验，交接可为列表或元组。合法但永不保留的交接仍可查询。未知计划报 `PlanNotFound`，非法起站、交接或传入 V1 计划报 `InvalidReviewRequest`。

公开路线按 V1 规则处理，回到已保留的公开站时擦除该站之后的后缀，实际复核阶段继续生效。分母是放行且最终保留指定交接的概率，分子是其中放行时已完成复核的概率。拒绝、滞留和永久循环均无放行贡献，按原转送概率口径核账。签出精确 `Fraction` 分母及完成比例。分母为零时比例为 `None`，分母为正且分子为零时比例为 `Fraction(0)`。

返回报告提供 `report_id`、`receipt`、`plan_id`、`revision_id`、`start`、`handoff`、`handoff_release_probability` 和 `review_completion_given_handoff_release`。`handoff` 在正文中为有序元组。报告、回执和交班条目同次提交。`before_commit` 与 V1 一样接收待提交的 `Receipt`，抛异常中断提交。提交失败报 `PublishError`，无新增报告或交班条目，可重试。`reports.history.read_report(archive, report_id)` 在重开后按号读取原报告及回执，未知号报 `ReportNotFound`。`reports.handover.handover(archive, plan_id)` 按该计划的实际签发顺序列示。更正和再签发不改变旧报告。保留 V1 接口、旧件编码、历史数据和全部原回归。

## 样例与运行

`review_examples.py` 提供两个工位计数样例。站元组与计数元组分别可用 `Station` 和 `TransferCount` 构造。`labels` 是 V2 接纳标签，`replacements` 是从原版提交的计数勘误。该文件也可直接运行，展示原项目在两版上的 V1 输出。

- `RESET_ON_RETURN` 中，从 A 走过 P 再走过 Q 后到达 B。B 等概率直接放行或经 C、R 回到 B。绕行会擦掉 C，R 仍重置复核。查询 A→B 的 `(分母, 比例)` 为 `(1, 1/2)`。交换 P 和 Q 的访问顺序后为 `(1, 0)`。以原修订为父，仅用 `label_only_patch` 清除 R 的标签后为 `(1, 1)`。原报告仍可领取 `(1, 1/2)`。原版查询 B→C 为 `(0, None)`。
- `PAIRED_EXIT` 中，从 A 出发的两支各占一半，B 和 C 随后都经见证站 Q 放行。原版经复检 P 的支路先到 B，勘误后先到 C。两版查询 A→B 的分母均为 `1/2`，复核完成比例依次为 `1` 和 `0`。

沿用 `.pointwise-runtime.json` 中的运行入口。`verify` 应执行原回归和本次联合核验，检查失败时返回非零。`demo` 应展示实际断源签发和勘误后重开领取。现有 `check_project.py` 从 `tests` 发现测试，`demo.py` 展示现有 V1 业务链。
