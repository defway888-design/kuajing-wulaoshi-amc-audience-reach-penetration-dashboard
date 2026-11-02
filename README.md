# 跨境吴老师 AMC 目标人群触达率看板 Skill

上传一份亚马逊营销云 AMC 的 Reach penetration within target audience Case 导出的 CSV，先检查表格格式，再生成可离线打开、可筛选和下载的单文件触达率看板。

## 适用场景

查看本次上传数据中的目标人群触达率，默认前10，可切换前50、前100或全部人群。支持只有 Sponsored Ads 的数据，也为 DSP 单独曝光和共同曝光保留列。不按月份拆分，不处理其他 AMC 报表或多期趋势。

## 运行前准备

- 准备一份本次运行 Reach penetration within target audience Case 后导出的 UTF-8 CSV，包含 `exposure`、`segment_id`、`segment_name`、`user_count`。具体允许值和计算见 [数据契约](references/data-contract.md)。
- 运行环境需要 Python 3.10 或更高版本；不需要第三方 Python 包、MCP 服务或联网图表库。Skill 不包含发布者本机路径或客户数据。

## 首次安装

这是公开仓库，无需提交 GitHub 用户名、接受私有仓库邀请或提供密码与令牌。将下面整段指令发送给 Codex：

```text
请从 https://github.com/defway888-design/kuajing-wulaoshi-amc-audience-reach-penetration-dashboard 安装跨境吴老师 AMC 目标人群触达率看板 Skill，并告诉我如何启动。
```

若当前会话尚未识别新安装的 Skill，按客户端提示刷新或重新打开会话。

## 启动方式

```text
使用 $kuajing-wulaoshi-amc-audience-reach-penetration-dashboard 生成看板。请先让我上传 Reach penetration within target audience Case 导出的 CSV，核验格式正确后再生成。
```

若启动消息已附 CSV，Skill 会直接核验该文件，不要求重复上传。

未附文件时，Skill 会先提示：`跨境吴老师需要您上传亚马逊营销云 AMC 中 Reach penetration within target audience 这个 Case 运行后导出的 CSV 数据报表，才能生成看板。请上传文件。`

## 执行结果与失败边界

Skill 先核验字段、编码、曝光类别、非负计数和人群记录。格式错误时会说明原因并停止，等待重新上传。格式通过后才生成一份带跨境吴老师 Logo 的离线 HTML。看板只含人群触达率表，默认前10，可切换前50、前100、全部，并下载当前筛选 CSV。缺失类别不按 0 计算；不完整人群不参与排名。

请只在自己的运行环境中处理真实客户 CSV；不要把客户数据、看板、密码或令牌提交到本公开仓库。

## 仓库文件

- [`SKILL.md`](SKILL.md)：执行入口与上传、核验、生成顺序。
- [`agents/openai.yaml`](agents/openai.yaml)：支持该文件的平台使用的显示名称与默认启动语。
- [`references/data-contract.md`](references/data-contract.md)：输入格式、异常和计算口径。
- [`assets/dashboard_template.html`](assets/dashboard_template.html)：内嵌品牌 Logo 的离线页面模板。
- [`scripts/audience_reach_dashboard.py`](scripts/audience_reach_dashboard.py)：标准库 CSV 核验与看板生成程序。
- [`scripts/selftest.py`](scripts/selftest.py)：无客户数据的逻辑自检。

## 版本更新记录

### v1.0.1｜2026-11-02

- 将运行时上传提示改为明确要求 Reach penetration within target audience Case 导出的 CSV，并同步更新启动说明。
- 影响范围：Skill 启动提示与文档；CSV 核验和看板计算规则未变。

### v1.0.0｜2026-11-01

- 首次封装单份 AMC 人群曝光 CSV 的上传、严格格式核验及离线看板生成流程。
- 影响范围：Skill 执行、数据核验、看板生成与公开仓库安装说明。
