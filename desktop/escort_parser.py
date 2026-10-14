"""Parse selected log bytes without inferring role identity or rendering HTML."""

from __future__ import annotations

import hashlib
import re
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone


PARSER_VERSION = 2
CHINA_TIME = timezone(timedelta(hours=8))
TIME = re.compile(r"^#W(\d{2}:\d{2}:\d{2})#n")
FILE_DATE = re.compile(r"(?:^|[_.-])(20\d{2})(\d{2})(\d{2})\d*(?=[_.-]|$)")
DEPOSIT = re.compile(r"你提交了#G([\d,]+)#n文游戏币#n作为押金")
REFUND = re.compile(r"你获得了#G([\d,]+)#n文游戏币#n。")
PAYOUT = re.compile(r"你获得了#cFF00FF([\d,]+)#n文(代金券|游戏币)")
BLESSING = re.compile(r"你获得了(.+?祝福)")
PIRATE = re.compile(r"击退了瓢把子，获得了#R(.+?)#n的奖励")
GRADE_DEPOSITS_PER_LEVEL = {"C级镖": 1050, "B级镖": 1575, "A级镖": 2100}


def decode_log(raw: bytes) -> str:
    encodings = (
        ("utf-16",)
        if raw.startswith((b"\xff\xfe", b"\xfe\xff"))
        else ("utf-8-sig", "gb18030")
    )
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                return text.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError:
            pass
    raise ValueError("日志编码无法识别，请使用 UTF-8、GB18030 或带 BOM 的 UTF-16 文本")


def fingerprint(raw: bytes) -> str:
    return hashlib.sha256(decode_log(raw).encode("utf-8")).hexdigest()


def date_from_filename(filename: str) -> date:
    match = FILE_DATE.search(filename)
    if not match:
        raise ValueError("文件名没有日期，原始日志正文只有时分秒，无法确定自然日")
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        raise ValueError("文件名中的日期无效") from None


def split_log_by_date(raw: bytes, first_date: date) -> dict[date, bytes]:
    """Split a timestamped log at local calendar-day boundaries."""
    lines = decode_log(raw).splitlines()
    buckets, pending = {}, []
    previous, day_offset, current_date = None, 0, None
    for line_number, line in enumerate(lines, 1):
        match = TIME.match(line)
        if match:
            try:
                clock = datetime.strptime(match[1], "%H:%M:%S").time()
            except ValueError:
                raise ValueError(f"第 {line_number} 行时间无效")
            seconds = clock.hour * 3600 + clock.minute * 60 + clock.second
            if previous is not None and seconds < previous:
                if previous - seconds > 12 * 3600:
                    day_offset += 1
                else:
                    raise ValueError(f"第 {line_number} 行时间倒序，无法可靠解析")
            previous = seconds
            current_date = first_date + timedelta(days=day_offset)
            buckets.setdefault(current_date, []).extend(pending)
            pending = []
        if current_date is None:
            pending.append(line)
        else:
            buckets[current_date].append(line)
    if pending and buckets:
        buckets[next(iter(buckets))] = pending + buckets[next(iter(buckets))]
    return {day: ("\n".join(day_lines) + "\n").encode("utf-8") for day, day_lines in buckets.items()}


def assign_grades(turns: list[dict], warnings: list[str]):
    # Infer one consistent level from the entire file. The supported coefficient
    # is for level 100+; neither the smallest amount nor a rounded quotient proves a grade.
    levels = None
    for amount in {turn["deposit"] for turn in turns}:
        candidates = {
            amount // unit
            for unit in GRADE_DEPOSITS_PER_LEVEL.values()
            if amount % unit == 0 and amount // unit >= 100
        }
        if candidates:
            levels = candidates if levels is None else levels & candidates
    level = next(iter(levels)) if levels and len(levels) == 1 else None
    for turn in turns:
        turn["grade"] = next(
            (
                grade
                for grade, unit in GRADE_DEPOSITS_PER_LEVEL.items()
                if level is not None and turn["deposit"] == level * unit
            ),
            "未知镖级",
        )
        if turn["grade"] == "未知镖级":
            warnings.append(
                f"第 {turn['number']} 轮押金 {turn['deposit']}：未知镖级（无法唯一匹配已确认的等级与押金规则）"
            )


def parse_log(raw: bytes, session_date: date) -> dict:
    text = decode_log(raw)
    turns, warnings = [], []
    current = None
    previous = None
    day_offset = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        match = TIME.match(line)
        if not match:
            continue
        try:
            clock = datetime.strptime(match[1], "%H:%M:%S").time()
        except ValueError:
            raise ValueError(f"第 {line_number} 行时间无效")
        seconds = clock.hour * 3600 + clock.minute * 60 + clock.second
        if previous is not None and seconds < previous:
            if previous - seconds > 12 * 3600:
                day_offset += 1
            else:
                raise ValueError(f"第 {line_number} 行时间倒序，无法可靠解析")
        previous = seconds
        now = datetime.combine(
            session_date + timedelta(days=day_offset), clock, CHINA_TIME
        ).isoformat()
        deposit = DEPOSIT.search(line)
        if deposit:
            amount = int(deposit[1].replace(",", ""))
            current = {
                "number": len(turns) + 1,
                "started_at": now,
                "settled_at": None,
                "deposit": amount,
                "refund": 0,
                "coins": 0,
                "vouchers": 0,
                "grade": "未知镖级",
                "blessings": [],
                "pirate_rewards": [],
                "encounters": 0,
            }
            turns.append(current)
            continue
        if current is None:
            if PAYOUT.search(line) or BLESSING.search(line) or REFUND.search(line):
                warnings.append(f"第 {line_number} 行结算缺少对应押金，未计入收益")
            continue
        refund = REFUND.search(line)
        payout = PAYOUT.search(line)
        blessing = BLESSING.search(line)
        pirate = PIRATE.search(line)
        if refund:
            amount = int(refund[1].replace(",", ""))
            if amount == current["deposit"]:
                current["refund"] += amount
                current["settled_at"] = now
            else:
                warnings.append(f"第 {line_number} 行游戏币到账与押金不符，未作为奖励或返还统计")
        if payout:
            current["vouchers" if payout[2] == "代金券" else "coins"] += int(
                payout[1].replace(",", "")
            )
            current["settled_at"] = now
        if blessing:
            current["blessings"].append(blessing[1])
            current["settled_at"] = now
        if pirate:
            current["pirate_rewards"].append({"at": now, "reward": pirate[1]})
        if "部分怪物受到了震慑" in line:
            current["encounters"] += 1
    if not turns:
        raise ValueError("未找到可识别的押镖轮次，请选择本场押镖日志")
    assign_grades(turns, warnings)
    for turn in turns:
        turn["seconds"] = (
            int(
                (
                    datetime.fromisoformat(turn["settled_at"])
                    - datetime.fromisoformat(turn["started_at"])
                ).total_seconds()
            )
            if turn["settled_at"]
            else None
        )
        if turn["settled_at"] is None:
            warnings.append(f"第 {turn['number']} 轮未结算")
    return {"turns": turns, "warnings": warnings, "parser_version": PARSER_VERSION}


def summarize(logs: list[dict], expected_roles: int) -> dict:
    unassigned_logs = [log for log in logs if log["role_id"] is None]
    logs = [log for log in logs if log["role_id"] is not None]
    entries = sorted(
        (
            dict(turn, role_id=log["role_id"])
            for log in logs
            for turn in log["parsed"]["turns"]
        ),
        key=lambda t: (t["started_at"], t["role_id"]),
    )
    # Build the complete candidate graph before matching: an ambiguous turn must
    # never win merely because its file happened to be processed first.
    candidates = {}
    starts = [datetime.fromisoformat(t["started_at"]).timestamp() for t in entries]
    for index, turn in enumerate(entries):
        candidates[index] = []
        for other_index in range(
            bisect_left(starts, starts[index] - 5),
            bisect_right(starts, starts[index] + 5),
        ):
            other = entries[other_index]
            if (
                turn["role_id"] != other["role_id"]
                and turn["deposit"] == other["deposit"]
            ):
                candidates[index].append(other_index)
    ambiguous, groups, used = set(), [], set()
    for index, turn in enumerate(entries):
        if index in used:
            continue
        component, pending = set(), [index]
        while pending:
            candidate = pending.pop()
            if candidate in component:
                continue
            component.add(candidate)
            pending.extend(j for j in candidates[candidate] if j not in component)
        matches = sorted(component)
        used.update(matches)
        # Multiple candidates for the same role or a transitive chain outside
        # the time tolerance makes the entire component ambiguous.
        if (
            len({entries[j]["role_id"] for j in matches}) != len(matches)
            or starts[matches[-1]] - starts[matches[0]] > 5
        ):
            ambiguous.update(matches)
            continue
        group = [entries[j] for j in matches]
        settled = [t["settled_at"] for t in group if t["settled_at"]]
        end = max(settled) if len(settled) == len(group) else None
        groups.append(
            {
                "number": len(groups) + 1,
                "started_at": turn["started_at"],
                "settled_at": end,
                "grade": turn["grade"],
                "deposit": turn["deposit"],
                "roles": group,
                "seconds": int(
                    (
                        datetime.fromisoformat(end)
                        - datetime.fromisoformat(turn["started_at"])
                    ).total_seconds()
                )
                if end
                else None,
                "incomplete": len(group) < expected_roles
                or any(t["settled_at"] is None for t in group),
            }
        )
    completed = [g for g in groups if g["settled_at"]]
    elapsed = (
        int(
            (
                max(datetime.fromisoformat(g["settled_at"]) for g in completed)
                - datetime.fromisoformat(completed[0]["started_at"])
            ).total_seconds()
        )
        if completed
        else 0
    )
    active = sum(g["seconds"] for g in completed)
    warnings = [
        f"角色{log['role_id']}：{warning}"
        for log in logs
        for warning in log["parsed"]["warnings"]
    ]
    if unassigned_logs:
        warnings.append(f"有 {len(unassigned_logs)} 份日志尚未分配角色，暂不计入收益和队伍轮次")
        warnings.extend(
            f"{log['filename']}：{warning}"
            for log in unassigned_logs
            for warning in log["parsed"]["warnings"]
        )
    if len(logs) < expected_roles:
        warnings.append(f"本场仅有 {len(logs)} / {expected_roles} 个角色的日志，数据不完整")
    if ambiguous:
        warnings.append(f"{len(ambiguous)} 条角色轮次匹配有歧义，未计入队伍趟数和效率")
    if any(g["incomplete"] for g in groups):
        warnings.append("部分队伍轮次缺少角色或结算记录，效率仅基于已识别时间线")
    roles = []
    for log in logs:
        turns = log["parsed"]["turns"]
        roles.append(
            {
                "role_id": log["role_id"],
                "coins": sum(t["coins"] for t in turns),
                "vouchers": sum(t["vouchers"] for t in turns),
                "deposit": sum(t["deposit"] for t in turns),
                "refund": sum(t["refund"] for t in turns),
                "completed_rounds": sum(bool(t["settled_at"]) for t in turns),
                "blessings": sum(len(t["blessings"]) for t in turns),
            }
        )
    totals = {
        key: sum(r[key] for r in roles)
        for key in ("coins", "vouchers", "deposit", "refund", "blessings")
    }
    efficiency_coins = sum(t["coins"] for g in completed for t in g["roles"])
    efficiency_vouchers = sum(t["vouchers"] for g in completed for t in g["roles"])
    totals.update(
        completed_rounds=len(completed),
        elapsed_seconds=max(elapsed, 0),
        active_seconds=active,
        efficiency_coins=efficiency_coins,
        efficiency_vouchers=efficiency_vouchers,
        average_seconds=round(active / len(completed), 2) if completed else 0,
        coins_per_hour=round(efficiency_coins * 3600 / elapsed, 2)
        if elapsed > 0
        else 0,
        vouchers_per_hour=round(efficiency_vouchers * 3600 / elapsed, 2)
        if elapsed > 0
        else 0,
    )
    return {
        "totals": totals,
        "roles": roles,
        "rounds": groups,
        "unaligned": [entries[i] for i in sorted(ambiguous)],
        "warnings": warnings,
    }
