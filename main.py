"""store-batch: 门店数据卡片 -> 企业微信发店长 -> 回传飞书跟进截图"""
import argparse
import json
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from feishu import Feishu, FeishuError, record_plain  # noqa: E402
from pause import PauseSignal, Pauser  # noqa: E402


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def get_feishu(cfg):
    sec = cfg.get("security") or {}
    allow = None
    if sec.get("allowed_app_token") and sec.get("allowed_table_id"):
        allow = (sec["allowed_app_token"], sec["allowed_table_id"])
    return Feishu(cfg["feishu"]["app_token"], cfg["feishu"]["table_id"], allowlist=allow)


def log(state, msg, force=False):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    if force or not state.get("_quiet"):
        print(line, flush=True)
    state.setdefault("_log", []).append(line)


def cleanup_store_files(cfg, store, chat_shot=None):
    cleanup_cfg = cfg.get("cleanup", {})
    if not cleanup_cfg.get("delete_local_after_upload", True):
        return 0
    targets = [ROOT / cfg["output"]["store_shot_dir"] / f"{store}.png"]
    if chat_shot:
        targets.append(Path(chat_shot))
    dry = ROOT / cfg["output"]["chat_shot_dir"] / f"{store}_dry.png"
    if dry.exists():
        targets.append(dry)
    removed = 0
    for p in targets:
        try:
            if Path(p).exists():
                Path(p).unlink()
                removed += 1
        except OSError:
            pass
    dbg = ROOT / "logs" / "debug"
    if dbg.exists():
        for p in list(dbg.glob(f"{store}_*.png")):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def save_state(state):
    out = {k: v for k, v in state.items() if not k.startswith("_")}
    (ROOT / "state.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if state.get("_log"):
        logdir = ROOT / "logs"
        logdir.mkdir(exist_ok=True)
        with open(logdir / f"run_{state.get('run_date', 'x')}.log", "a", encoding="utf-8") as f:
            f.write("\n".join(state["_log"]) + "\n")
        state["_log"] = []


def load_state():
    p = ROOT / "state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"runs": {}}


def round_field_names(cfg, round_date=None):
    f = cfg["feishu"]["fields"]
    if round_date:
        tag = f"{int(round_date.split('-')[1])}.{int(round_date.split('-')[2])}"
        return f["date_screenshot"].format(date=tag), f["date_time"].format(date=tag)
    return f["screenshot"], None


def ensure_round_fields(feishu, cfg, round_date, state):
    if not round_date:
        return
    shot_field, time_field = round_field_names(cfg, round_date)
    existing = {f["field_name"] for f in feishu.list_fields()}
    if shot_field not in existing:
        feishu.create_field(shot_field, 17)
        log(state, f"创建字段: {shot_field} (附件)")
    if time_field not in existing:
        feishu.create_field(time_field, 5, {"date_formatter": "yyyy/MM/dd HH:mm"})
        log(state, f"创建字段: {time_field} (日期)")


def tier_of(pr, vals):
    """返回门店命中的优先级序号；不在任何 tier 内返回 None（排除）。"""
    t = vals.get(pr.get("type_field"))
    g = vals.get(pr.get("target_field"))
    for i, tier in enumerate(pr.get("tiers", [])):
        if t in tier.get("types", []) and g == tier.get("target"):
            return i
    return None


def collect_targets(cfg, feishu, field, state, limit=None, store=None):
    name_field = cfg["feishu"]["fields"]["store_name"]
    mgr_field = cfg["feishu"]["fields"]["manager"]
    skip_stores = cfg.get("skip_stores", {})
    pr = cfg.get("priority") or {}
    extra = [pr.get("type_field"), pr.get("target_field")] if pr.get("enabled") else []
    field_names = list(dict.fromkeys(
        [name_field, mgr_field, field] + cfg["feishu"]["card_fields"] + [x for x in extra if x]
    ))
    targets, skipped = [], []
    for rec in feishu.iter_records(
        view_id=cfg["feishu"].get("view_id"),
        field_names=field_names,
        page_size=500,
    ):
        vals = record_plain(rec.get("fields", {}))
        name = vals.get(name_field)
        mgr = vals.get(mgr_field)
        if store and name != store:
            continue
        if name in skip_stores:
            skipped.append(f"{name}(人工核对: {skip_stores[name]})")
            continue
        if vals.get(field):
            skipped.append(name)
            continue
        if not name or not mgr:
            skipped.append(f"{name}(缺店长或店名)")
            continue
        tier = None
        if pr.get("enabled"):
            tier = tier_of(pr, vals)
            if tier is None:
                t = vals.get(pr.get("type_field")) or "未分类"
                skipped.append(f"{name}(类型不在跟进清单: {t})")
                continue
        targets.append({
            "record_id": rec["record_id"], "store": name,
            "manager": mgr, "values": vals, "tier": tier,
        })
    if pr.get("enabled"):
        targets.sort(key=lambda x: x["tier"])  # 稳定排序：同优先级保持视图原顺序
    return targets, skipped


def batch_targets(cfg, targets, limit=None):
    """按批次大小取目标；clamp_to_tier 时确保一批不跨优先级。"""
    pr = cfg.get("priority") or {}
    bs = limit or (pr.get("batch_size") if pr.get("enabled") else None)
    if not bs:
        return targets
    if pr.get("enabled") and pr.get("clamp_to_tier") and targets:
        first_tier = targets[0]["tier"]
        same = 0
        for t in targets:
            if t["tier"] != first_tier:
                break
            same += 1
        bs = min(bs, same)
    return targets[:bs]


def cmd_preview(args):
    cfg = load_config()
    feishu = get_feishu(cfg)
    state = load_state()
    state.setdefault("_log", [])
    ensure_round_fields(feishu, cfg, args.round_date, state)
    field, _ = round_field_names(cfg, args.round_date)
    all_targets, skipped = collect_targets(cfg, feishu, field, state, None, args.store)
    targets = batch_targets(cfg, all_targets, args.limit)
    pr = cfg.get("priority") or {}
    labels = [t.get("label", f"T{i+1}") for i, t in enumerate(pr.get("tiers", []))]
    print(f"目标字段: {field}    本批: {len(targets)} 家 / 待处理总数: {len(all_targets)} 家"
          f"    已跳过(已有截图/缺信息/不在清单): {len(skipped)} 家")
    if pr.get("enabled"):
        counts = {}
        for t in all_targets:
            counts[t["tier"]] = counts.get(t["tier"], 0) + 1
        print("优先级待处理分布:")
        for i, lab in enumerate(labels):
            print(f"  {lab}: {counts.get(i, 0)} 家")
    for i, t in enumerate(targets, 1):
        tier_lab = labels[t["tier"]] if t.get("tier") is not None and t["tier"] < len(labels) else "-"
        print(f"{i:4d}. [{tier_lab}] {t['store']}  ->  店长: {t['manager']}   [{t['record_id']}]")
    if skipped[:10]:
        print("跳过示例:", ", ".join(str(s) for s in skipped[:10]))
    return 0


def run_one(cfg, feishu, state, target, field, time_field, dry_run=False, pauser=None):
    store, manager, rid = target["store"], target["manager"], target["record_id"]
    from card import make_card

    def chk():
        if pauser:
            pauser.checkpoint()

    chk()
    card_path = ROOT / cfg["output"]["store_shot_dir"] / f"{store}.png"
    make_card(store, target["values"], cfg["feishu"]["card_fields"], card_path)
    log(state, f"卡片已生成: {card_path.name}")

    from wecom import WeCom, WeComError

    chk()
    wc = WeCom(cfg)
    wc.ensure_ready()
    chk()
    dept = wc.search_store(store, tag=f"{store}_")
    chk()
    wc.open_manager_chat(store, manager, tag=f"{store}_", dept=dept)
    log(state, f"已打开会话: {manager} ({store})")
    chk()

    if dry_run:
        shot = wc.capture_chat(ROOT / cfg["output"]["chat_shot_dir"] / f"{store}_dry.png", tag=f"{store}_")
        log(state, f"dry-run 完成，会话截图: {shot.name}")
        return {"chat_shot": str(shot)}

    chk()
    marker = ROOT / "cache" / f"{rid}.text_sent"
    skip_text = marker.exists() and (time.time() - marker.stat().st_mtime) < 2 * 3600
    if not skip_text:
        wc.send_text(cfg["message"], tag=f"{store}_")
        marker.parent.mkdir(exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        log(state, "文字已发送")
    else:
        log(state, "检测到文字已发送标记，跳过重发文字")
    chk()
    wc.send_image(card_path, tag=f"{store}_")
    log(state, "图片已发送")
    if marker.exists():
        marker.unlink()

    chk()
    chat_shot = wc.capture_chat(
        ROOT / cfg["output"]["chat_shot_dir"] / f"{datetime.now():%m%d}" / f"{store}.png",
        tag=f"{store}_",
    )
    log(state, f"会话截图: {chat_shot}")

    chk()
    rec = feishu.get_record(rid)
    if record_plain(rec.get("fields", {})).get(field):
        log(state, f"警告: {field} 已有内容，跳过上传（可能被其他人填写）")
        return {"chat_shot": str(chat_shot), "uploaded": False}

    token = feishu.upload_media(chat_shot)
    fields = {field: [{"file_token": token}]}
    if time_field:
        fields[time_field] = int(time.time() * 1000)
    feishu.update_record(rid, fields)
    log(state, f"已上传到 {field}" + (f" + {time_field}" if time_field else ""))
    removed = cleanup_store_files(cfg, store, chat_shot)
    if removed:
        log(state, f"已清理本地图片 {removed} 个（飞书已保留）")
    return {"chat_shot": str(chat_shot), "uploaded": True, "file_token": token}


def cmd_run(args):
    cfg = load_config()
    feishu = get_feishu(cfg)
    state = load_state()
    run_date = args.round_date or date.today().isoformat()
    field, time_field = round_field_names(cfg, args.round_date)
    state.setdefault("runs", {}).setdefault(run_date, {"field": field, "done": {}, "failed": {}})
    state["run_date"] = run_date
    state["_log"] = []
    state["_quiet"] = bool(getattr(args, "quiet", False))

    ensure_round_fields(feishu, cfg, args.round_date, state)
    all_targets, skipped = collect_targets(cfg, feishu, field, state, None, args.store)
    done = state["runs"][run_date]["done"]
    remaining = [t for t in all_targets if t["record_id"] not in done]
    targets = batch_targets(cfg, remaining, args.limit)
    pr = cfg.get("priority") or {}
    labels = [t.get("label", f"T{i+1}") for i, t in enumerate(pr.get("tiers", []))]
    tier_lab = "-"
    if targets and targets[0].get("tier") is not None and targets[0]["tier"] < len(labels):
        tier_lab = labels[targets[0]["tier"]]
    log(state, f"目标字段={field} 本批={len(targets)} 待处理={len(remaining)} 跳过={len(skipped)} 当前优先级={tier_lab}", force=True)
    if not targets:
        log(state, "没有需要处理的门店", force=True)
        save_state(state)
        return 0

    if not state["_quiet"]:
        print(f"待处理 {len(targets)} 家:")
        for i, t in enumerate(targets, 1):
            print(f"  {i:3d}. {t['store']} -> {t['manager']}")

    if not args.yes:
        ans = input("确认开始执行? 输入 y 继续: ").strip().lower()
        if ans != "y":
            print("已取消")
            return 0

    interval = cfg["wecom"]
    pause_cfg = cfg.get("pause") or {}
    pauser = Pauser(enabled=bool(pause_cfg.get("enabled", True)) and not args.dry_run)
    processed_ok, processed_fail = 0, 0
    try:
        i = 0
        while i < len(targets):
            t = targets[i]
            pauser.gate()
            store, manager, rid = t["store"], t["manager"], t["record_id"]
            log(state, f"[{i + 1}/{len(targets)}] 开始: {store} -> {manager}")
            try:
                result = run_one(cfg, feishu, state, t, field, time_field,
                                 dry_run=args.dry_run, pauser=pauser)
                if not args.dry_run:
                    done[rid] = {
                        "store": store,
                        "manager": manager,
                        "chat_shot": result.get("chat_shot"),
                        "uploaded": result.get("uploaded", False),
                        "ts": datetime.now().isoformat(timespec="seconds"),
                    }
                processed_ok += 1
            except PauseSignal:
                log(state, f"已暂停：{store} 未完成，恢复后将重试", force=True)
                pauser.gate()
                continue
            except Exception as e:
                state["runs"][run_date]["failed"][rid] = {
                    "store": store, "manager": manager,
                    "error": str(e), "ts": datetime.now().isoformat(timespec="seconds"),
                }
                processed_fail += 1
                log(state, f"失败: {store} -> {e}", force=True)
            save_state(state)
            i += 1
            if i < len(targets):
                delay = random.uniform(interval["send_interval_min_sec"], interval["send_interval_max_sec"])
                pauser.sleep(delay)
    finally:
        pauser.stop()

    log(state, f"本轮完成: 成功 {processed_ok} 失败 {processed_fail}", force=True)
    save_state(state)
    return 0


def cmd_status(args):
    cfg = load_config()
    feishu = get_feishu(cfg)
    state = load_state()
    total_done = 0
    for day, run in sorted(state.get("runs", {}).items()):
        d = len(run.get("done", {}))
        f = len([1 for rid in run.get("failed", {}) if rid not in run.get("done", {})])
        total_done += d
        print(f"{day}  字段={run.get('field')}  成功={d}  未成功={f}")
    field, _ = round_field_names(cfg, getattr(args, "round_date", None))
    targets, skipped = collect_targets(cfg, feishu, field, {}, None, None)
    print(f"当前字段「{field}」剩余待处理 {len(targets)} 家，跳过 {len(skipped)} 家")
    pr = cfg.get("priority") or {}
    if pr.get("enabled"):
        labels = [t.get("label", f"T{i+1}") for i, t in enumerate(pr.get("tiers", []))]
        counts = {}
        for t in targets:
            counts[t["tier"]] = counts.get(t["tier"], 0) + 1
        for i, lab in enumerate(labels):
            print(f"  {lab}: {counts.get(i, 0)} 家")
    fails = {}
    for day, run in state.get("runs", {}).items():
        for rid, info in run.get("failed", {}).items():
            if rid not in run.get("done", {}):
                fails[info.get("store") or rid] = (info.get("error") or "")[:70]
    if fails:
        print(f"历史失败(未成功) {len(fails)} 家:")
        for s, e in list(fails.items())[:40]:
            print(f"  - {s}: {e}")
    return 0


def cmd_cleanup(args):
    cfg = load_config()
    state = load_state()
    keep_stores = set()
    if not args.drop_failed:
        for day, run in state.get("runs", {}).items():
            for rid, info in run.get("failed", {}).items():
                if rid not in run.get("done", {}) and info.get("store"):
                    keep_stores.add(info["store"])
    freed = removed = 0

    def rm(p):
        nonlocal freed, removed
        try:
            size = p.stat().st_size
            p.unlink()
            freed += size
            removed += 1
        except OSError:
            pass

    for p in (ROOT / "shots" / "search").glob("*.png"):
        rm(p)
    for p in (ROOT / "shots" / "store").glob("*.png"):
        rm(p)
    chat_dir = ROOT / "shots" / "chat"
    if chat_dir.exists():
        for p in chat_dir.rglob("*_dry.png"):
            rm(p)
        if args.include_chat:
            for p in chat_dir.rglob("*.png"):
                rm(p)
    dbg = ROOT / "logs" / "debug"
    if dbg.exists():
        for p in dbg.glob("*.png"):
            if any(p.name.startswith(s + "_") for s in keep_stores):
                continue
            rm(p)
    print(f"清理完成: 删除 {removed} 个文件, 释放 {freed / 1048576:.1f} MB, 保留失败证据 {len(keep_stores)} 家")
    return 0


def find_store(cfg, feishu, store_name):
    name_field = cfg["feishu"]["fields"]["store_name"]
    field_names = list(set(cfg["feishu"]["card_fields"]) | {name_field, cfg["feishu"]["fields"]["manager"]})
    for rec in feishu.iter_records(
        view_id=cfg["feishu"].get("view_id"), field_names=field_names, page_size=500
    ):
        vals = record_plain(rec.get("fields", {}))
        if vals.get(name_field) == store_name:
            return rec["record_id"], vals
    return None, None


def cmd_card(args):
    cfg = load_config()
    feishu = get_feishu(cfg)
    rid, vals = find_store(cfg, feishu, args.store)
    if not rid:
        print(f"[card] store not found: {args.store}")
        return 1
    from card import make_card

    out = ROOT / cfg["output"]["store_shot_dir"] / f"{args.store}.png"
    make_card(args.store, vals, cfg["feishu"]["card_fields"], out)
    print(json.dumps({"record_id": rid, "store": args.store, "image": str(out)}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(prog="store-batch")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("card", help="生成单个门店卡片图（测试用）")
    p.add_argument("store", help="oa门店名称")
    p.set_defaults(func=cmd_card)

    p = sub.add_parser("preview", help="列出待处理门店清单")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--store", default=None)
    p.add_argument("--round-date", default=None, help="YYYY-MM-DD，指定后使用当日字段")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("run", help="执行发送流程")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--store", default=None)
    p.add_argument("--round-date", default=None)
    p.add_argument("--dry-run", action="store_true", help="只走到打开会话并截图，不发送")
    p.add_argument("--yes", action="store_true", help="跳过人工确认")
    p.add_argument("--quiet", action="store_true", help="只输出汇总与失败清单")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="查看进度汇总")
    p.add_argument("--round-date", default=None)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("cleanup", help="清理历史本地图片")
    p.add_argument("--include-chat", action="store_true", help="连已归档的会话截图一起删")
    p.add_argument("--drop-failed", action="store_true", help="连失败门店的证据图也删")
    p.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
