# 澄屿材料试验线返修路线复盘

澄屿材料试验室按台架转送件次记录复合材料试板的返修流程。记录员接纳或更正计数，工艺员按固定修订定版并核查试走，质量分析员在源库关闭后复盘放行与保留交接，交班人员凭正式编号复领。

## 运行

需要 Python 3.11，仅使用标准库。从工程根目录运行控制台提供的完整回归入口和业务演示。

```sh
python3 -B check_project.py
python3 -B demo.py
```

演示使用两份临时 SQLite 文件，从 `samples/shift.json` 的台架计数实际定版、停源试走和签发，随后勘误、再定版并重开报告库复领。样例在 A 行给 B `1/4`、C `1/2`、永不到达 `1/4`。实走 A、B、A、C 最终保留 A、C。原报告放行 `3/7`，放行中保留 A→B 的比例 `1/3`。撤销 A 到私有门的转送后，新计划签出 `1/2` 和 `0`，原号仍能领取旧报告。

## Python 接口

```python
from contextlib import closing
from fractions import Fraction

from analysis.request import publish_report
from plans.freeze import freeze_plan
from plans.snapshot import PlanOutcome
from reports.handover import handover
from reports.history import read_report
from reports.storage import open_archive
from source.intake import receive
from source.revisions import Station, TransferCount
from source.storage import open_source
from walks.replay import replay_walk

with closing(open_archive('review.sqlite3')) as archive:
    with closing(open_source('bench.sqlite3')) as source:
        revision = receive(
            source, 'bench-01', [Station('A', True), Station('B', True)], 'pass', 'fail',
            [TransferCount('A', 'B', 4), TransferCount('B', 'pass', 4)],
        )
        plan = freeze_plan(source, archive, revision)
    walk = replay_walk(archive, plan.plan_id, 'A', ('B', PlanOutcome.RELEASE))
    report = publish_report(archive, plan.plan_id, 'A', ('A', 'B'))
    assert walk.retained == ('A', 'B')
    assert report.retention_given_release == Fraction(1)
    assert read_report(archive, report.report_id) == report
    assert handover(archive, plan.plan_id)[0].report_id == report.report_id
```

- `source.storage.open_source(path)` 和 `reports.storage.open_archive(path)` 返回独立 SQLite 连接。调用方关闭连接。`initialize_source(connection)` 和 `initialize_archive(connection)` 可在空闲连接上重复调用，保留已接纳的批次及归档成果。
- `source.intake.receive(source, batch, stations, release, reject, counts)` 返回整数修订号。站和终局用非空区分大小写的名字，终局名字彼此及与各站不同。公开站有一至六个。计数是非负整数，单位为转送件次，`bool` 不作整数。只允许从具名站发出，目标可以是具名站或终局。非法输入抛 `InvalidCounts`，冲突批号抛 `BatchConflict`，均无新增修订。
- `source.corrections.amend(source, parent_id, replacements)` 按有向键替换父修订中的计数，每键最多提交一个替换值。零撤销该转送，未列键从该父版继承。返回独立修订号，旧修订及父关系可通过 `source.revisions.load_revision` 按号领取。未知父修订抛 `RevisionNotFound`，非法计数抛 `InvalidCounts`。
- `plans.freeze.freeze_plan(source, archive, revision_id)` 返回 `FixedPlan`。`plans.catalog.load_plan(archive, plan_id)` 重开后可按号取得同一计划，未知计划抛 `PlanNotFound`。不可读的修订、核账或计划写入失败抛 `FreezeError`，无新计划。
- `walks.replay.replay_walk(archive, plan_id, start, outcomes)` 接收起站之后的逐步结果，公开站为字符串，终结结果为 `PlanOutcome` 枚举。`WalkResult` 提供 `actual`、`retained`、`erasures`、`retained_handoffs` 和 `terminal`。非法起站、零概率步骤、终局后有步骤或步序缺终局抛 `InvalidWalk`，未知计划抛 `PlanNotFound`。
- `analysis.request.publish_report(archive, plan_id, start, handoff, *, before_commit=None)` 返回 `FormalReport`，其中有 `receipt`、`report_id` 和 `plan_id`。起站和一对有向交接端点必须是该计划的公开站，合法端点之间的零概率交接仍可查询。未知计划抛 `PlanNotFound`，非法起站或交接抛 `InvalidReviewRequest`。提交前接点接收待提交的 `Receipt`，供调用方观察或以异常终止提交。接点在事务中执行，只读视察或抛出异常均可，事务控制由签发负责。签发异常抛 `PublishError`，没有成功回执。
- `reports.history.read_report(archive, report_id)` 从已提交正文恢复原报告及回执，未知号抛 `ReportNotFound`。`reports.handover.handover(archive, plan_id)` 返回按正式签发先后排列的 `HandoverEntry(report_id, start)` 列表。已知空计划返回空列表，未知计划抛 `PlanNotFound`。

## 核账口径

计数中的同向重复行按件次合加，按出发站总件次归一。`FixedPlan.row_for(station)` 依次返回按声明顺序排列的公开站列，以及 `PlanOutcome.RELEASE`、`REJECT`、`NEVER` 列。私有转送一直解释到首次到达公开站或终局。无可观测出边及私有路径永不到达都计入 `NEVER`。回到同一公开站也占其对应列。各列值均为精确 `Fraction`，每行合计为一。计划持久化只含公开账和固定来源号，私有定义及原计数在源库。

试走只用给定选步。每步从当前公开站按正概率验证，再把实际到达追加至轨迹。回到保留路线中的工位时，截掉它之后的后缀并留存擦除记录。终点单独记录，耗尽输入不能推断终点。

放行概率采用原始转送口径，拒绝、私有滞留、公开永久循环贡献零。放行报告的条件值按最终保留路线计算，分母为全部放行质量，分子为放行且最终保留指定有向交接的联合质量。实现按简单终局路线分解末次离站，精确计入可擦除回返。放行率为零时条件值为 `None`，有放行而该交接未保留时为 `Fraction(0)`。正文和交班条目同一事务提交，以实际提交顺序列示。勘误产生新的来源与计划编号，已签报告读取时按原号恢复而不重算。
