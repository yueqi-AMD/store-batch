---
name: store-batch
description: "连锁门店运营跟进自动化（飞书多维表格 × 企业微信）：批量筛选门店、生成一店一图数据卡片、企微定向发送店长、会话截图回传飞书归档；内置 OCR 三重身份校验、发送结果验证、幂等断点续跑与 Ctrl+Z 安全暂停。当需要批量跟进连锁门店（运营数据分发 / 达标提醒 / 回执归档）时使用。"
license: MIT
metadata:
  author: store-batch contributors
  version: 1.0.0
---

# store-batch 技能

## 何时使用

- 用户要求「批量给门店店长发运营数据 / 达标提醒」「门店跟进」「数据分发并回传归档」
- 环境为 Windows + 企业微信桌面版 + 飞书多维表格

## 不适用

- 非 Windows 环境（GUI 自动化依赖 Windows API）
- 飞书多维表格之外的数据源
- 需要给非企业微信联系人发送消息的场景

## 前置检查（执行前必须确认）

1. `config.json` 已从 `config.example.json` 复制并填写（app_token / table_id / 字段映射 / 话术）
2. 环境变量 `LARK_APP_ID` / `LARK_APP_SECRET` 已设置
3. 企业微信已登录，主窗口可最大化
4. 告知用户：运行期间不要操作鼠标键盘；`Ctrl+Z` 可暂停 / 继续

## 执行流程

1. `python main.py preview --limit 30` 查看本批目标
2. `python main.py run --limit 30 --dry-run`（可选）只走到打开会话并截图，不发送
3. `python main.py run --limit 30 --yes --quiet` 正式执行
4. `python main.py status` 查看进度与失败清单
5. 失败门店人工核对或重跑（幂等）；门店/店长数据不一致的加入 `config.json` 的 `skip_stores`

## 关键文件

- `main.py` 流程编排 / `card.py` 卡片渲染 / `feishu.py` 飞书 API / `wecom.py` 企微 UI 自动化 / `pause.py` 暂停热键
- `probe_*.py` 界面校准工具（改动分辨率或企微版本更新后使用）

## 硬性规则

- 只操作 `config.json` 指定的多维表格与其字段；如配置了 `security` 白名单则严格锁定
- 运行期间不抢焦点；失败门店不要反复轰炸式重试
- 发送节流保持默认（8-15 秒/家），不要调小
- 「数据不一致」类失败绝不猜测发送，一律登记人工核对
