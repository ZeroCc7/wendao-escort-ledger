"""Desktop accounting: synchronous teams and explicit reward choices."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from desktop.escort_parser import CHINA_TIME, DEPOSIT, GRADE_DEPOSITS_PER_LEVEL, TIME, parse_log, decode_log


ANALYSIS_VERSION = 2
CHOICE = re.compile(r"队伍选择获得#R(碰碰运气|普通收益)#n(?:[，,](.*))?")
COLOR = re.compile(r"#c[0-9a-fA-F]{6}|#[A-Zn]")
MULTIPLIER = re.compile(r"(\d+(?:\.\d+)?)倍")
ROSTER = re.compile(r"由于你队伍中的(.+?)为#@年费会员")
NAME = re.compile(r"#Y(.+?)#n")
JOIN_LEADER = re.compile(r"你加入#Y#<(.+?)#>#n的队伍")
JOIN_MEMBER = re.compile(r"#Y#<(.+?)#>#n加入了队伍")
SERVER = re.compile(r"你在#Y【(.+?)】[^#]*#n上线啦")
REPUTATION = re.compile(r"声望值#n增加了#R([\d,]+)#n点")
MEDICINE = re.compile(r"你使用了(\d+)个药品以恢复")
TALISMAN = re.compile(r"你消耗了#R([\d,]+)#n点八卦神符耐久度")


def parse_desktop_log(raw, day):
    parsed = parse_log(raw, day)
    current = None
    index = 0
    identity_events = []
    for line in decode_log(raw).splitlines():
        clock = TIME.match(line)
        if not clock:
            continue
        at = datetime.combine(day, datetime.strptime(clock[1], "%H:%M:%S").time(), CHINA_TIME)
        roster = ROSTER.search(line)
        if roster:
            names = sorted(set(NAME.findall(roster[1])))
            if len(names) == 5:
                identity_events.append({"at": at.isoformat(), "kind": "roster", "names": names})
        for pattern, kind in ((JOIN_LEADER, "leader"), (JOIN_MEMBER, "join")):
            for name in pattern.findall(line):
                identity_events.append({"at": at.isoformat(), "kind": kind, "name": name})
        server = SERVER.search(line)
        if server:
            identity_events.append({"at": at.isoformat(), "kind": "server", "name": server[1]})
        if DEPOSIT.search(line):
            current = parsed["turns"][index]
            current.update(reward_choice=None, luck_result="", reward_multiplier=None,
                           reputation=0, medicine_count=0, talisman_durability=0)
            index += 1
        choice = CHOICE.search(line)
        if current is None or at < datetime.fromisoformat(current["started_at"]):
            continue
        end = current["settled_at"]
        if end and at > datetime.fromisoformat(end):
            continue
        if choice:
            current["reward_choice"] = choice[1]
            if choice[1] == "碰碰运气":
                result = COLOR.sub("", choice[2] or "").removeprefix("你获得了").rstrip("。")
                current["luck_result"] = result or "结果未记录"
                multiple = MULTIPLIER.search(result)
                current["reward_multiplier"] = float(multiple[1]) if multiple else 2.0 if "翻倍" in result else None
        for pattern, field in ((REPUTATION, "reputation"), (MEDICINE, "medicine_count"),
                               (TALISMAN, "talisman_durability")):
            match = pattern.search(line)
            if match:
                current[field] += int(match[1].replace(",", ""))
    parsed["identity_events"] = identity_events
    parsed["desktop_analysis_version"] = ANALYSIS_VERSION
    return parsed


def seconds(value):
    return datetime.fromisoformat(value).timestamp()


def synchronous(group, entry):
    """Five seconds of client logging jitter; different levels may pay different deposits."""
    starts = [seconds(t["started_at"]) for t in [*group, entry]]
    ends = [seconds(t["settled_at"]) for t in [*group, entry] if t["settled_at"]]
    return (entry["source_key"] not in {t["source_key"] for t in group}
            and max(starts) - min(starts) <= 5
            and (not ends or max(ends) - min(ends) <= 5))


def split_teams(logs):
    entries = sorted(
        [dict(turn, source_key=log["source_key"], filename=log["filename"], path=log["path"])
         for log in logs for turn in log["parsed"]["turns"]],
        key=lambda t: (t["started_at"], t["source_key"]),
    )
    rounds = []
    for entry in entries:
        candidates = [group for group in reversed(rounds)
                      if seconds(entry["started_at"]) - seconds(group[0]["started_at"]) <= 5
                      and synchronous(group, entry)]
        if len(candidates) == 1:
            candidates[0].append(entry)
        else:
            rounds.append([entry])
    teams = []
    for group in rounds:
        members = {t["source_key"] for t in group}
        if len(members) > 5:
            # Timing alone cannot identify two perfectly simultaneous full teams.
            # Preserve all money, but do not invent a six-person team.
            for entry in group:
                team = next((team for team in teams if team.get("uncertain")
                             and entry["source_key"] in team["members"]), None)
                if team is None:
                    team = {"members": {entry["source_key"]}, "rounds": [], "uncertain": True}
                    teams.append(team)
                team["rounds"].append([entry])
            continue
        candidates = [team for team in teams if not team.get("uncertain")
                      and team["members"] & members and len(team["members"] | members) <= 5]
        # When a character switches teams, use the most recent compatible roster.
        team = max(candidates, key=lambda t: t["rounds"][-1][0]["started_at"]) if candidates else None
        if team is None:
            team = {"members": set(), "rounds": []}
            teams.append(team)
        team["members"].update(members)
        team["rounds"].append(group)
    for index, team in enumerate(teams, 1):
        team["id"] = hashlib.sha256("\n".join(sorted(team["members"])).encode()).hexdigest()[:16]
        team["name"] = f"队伍{index}" if not team.get("uncertain") else f"待确认{index}"
    return teams


def totals_for(roles, rounds):
    totals = {key: sum(role[key] for role in roles)
              for key in ("coins", "vouchers", "deposit", "refund", "luck_count", "multiplier_count")}
    completed = [r for r in rounds if r["settled_at"]]
    elapsed = max(0, seconds(max(r["settled_at"] for r in completed)) - seconds(min(r["started_at"] for r in completed))) if completed else 0
    active = sum(r["seconds"] for r in completed)
    totals.update(completed_rounds=len(completed), elapsed_seconds=int(elapsed), active_seconds=active,
                  luck_rounds=sum(r["luck_selected"] for r in rounds),
                  average_seconds=round(active / len(completed), 2) if completed else 0)
    return totals


def rates(totals):
    elapsed = totals["elapsed_seconds"]
    totals["coins_per_hour"] = round(totals["coins"] * 3600 / elapsed, 2) if elapsed else 0
    totals["vouchers_per_hour"] = round(totals["vouchers"] * 3600 / elapsed, 2) if elapsed else 0
    return totals


def identify_members(team, logs):
    """Use a consistent five-person roster and four observed other names."""
    start = datetime.fromisoformat(team["rounds"][0][0]["started_at"])
    begin = start - timedelta(hours=8)
    events = {key: [event for log in logs if log["source_key"] == key
                    for event in log["parsed"].get("identity_events", [])
                    if begin <= datetime.fromisoformat(event["at"]) <= start]
              for key in team["members"]}
    leaders = {event["name"] for source_events in events.values() for event in source_events
               if event["kind"] == "leader"}
    servers = {event["name"] for source_events in events.values() for event in source_events
               if event["kind"] == "server"}
    context = {"leader_name": next(iter(leaders)) if len(leaders) == 1 else None,
               "server_name": next(iter(servers)) if len(servers) == 1 else None}
    if len(team["members"]) != 5 or team.get("uncertain"):
        return {}, context
    rosters = {frozenset(event["names"]) for source_events in events.values()
               for event in source_events if event["kind"] == "roster"}
    if len(rosters) != 1:
        return {}, context
    roster = next(iter(rosters))
    others = {key: {event["name"] for event in source_events if event["kind"] == "join"}
              for key, source_events in events.items()}
    for key, source_events in events.items():
        others[key].update(event["name"] for event in source_events if event["kind"] == "leader")
    if set().union(*others.values()) != roster:
        return {}, context
    direct = {key: next(iter(roster - names)) for key, names in others.items()
              if len(names) == 4 and names <= roster}
    if len(set(direct.values())) != len(direct):
        return {}, context
    found = {key: {"name": name, "name_source": "入队记录"} for key, name in direct.items()}
    remaining_keys = team["members"] - direct.keys()
    remaining_names = roster - set(direct.values())
    if len(remaining_keys) == len(remaining_names) == 1:
        found[next(iter(remaining_keys))] = {"name": next(iter(remaining_names)), "name_source": "队伍排除"}
    return found, context


def summarize_team(team, logs, saved_order):
    keys = sorted(team["members"])
    preferred = saved_order.get(team["id"], {})
    order = dict(preferred) if set(preferred) == set(keys) and set(preferred.values()) == set(range(1, len(keys) + 1)) else {key: i for i, key in enumerate(keys, 1)}
    identity, context = identify_members(team, logs)
    roles, team_logs, rounds = [], [], []
    for key in keys:
        turns = [dict(turn, role_id=order[key], character_name=identity.get(key, {}).get("name"),
                      name_source=identity.get(key, {}).get("name_source"))
                 for group in team["rounds"] for turn in group if turn["source_key"] == key]
        sources = [log for log in logs if log["source_key"] == key]
        role = {"role_id": order[key], "team_id": team["id"], "team_name": team["name"],
                "character_name": identity.get(key, {}).get("name"),
                "name_source": identity.get(key, {}).get("name_source")}
        role.update({field: sum(t[field] for t in turns) for field in ("coins", "vouchers", "deposit", "refund")})
        levels = {t["deposit"] // GRADE_DEPOSITS_PER_LEVEL[t["grade"]] for t in turns
                  if t["grade"] in GRADE_DEPOSITS_PER_LEVEL
                  and t["deposit"] % GRADE_DEPOSITS_PER_LEVEL[t["grade"]] == 0}
        role.update(completed_rounds=sum(bool(t["settled_at"]) for t in turns),
                    luck_count=sum(t.get("reward_choice") == "碰碰运气" for t in turns),
                    multiplier_count=sum((t.get("reward_multiplier") or 0) > 1 for t in turns),
                    level_estimate=next(iter(levels)) if len(levels) == 1 else None,
                    pirate_reward_count=sum(len(t["pirate_rewards"]) for t in turns),
                    reputation=sum(t.get("reputation", 0) for t in turns),
                    medicine_count=sum(t.get("medicine_count", 0) for t in turns),
                    talisman_durability=sum(t.get("talisman_durability", 0) for t in turns),
                    encounters=sum(t["encounters"] for t in turns))
        roles.append(role)
        team_logs.append(dict(sources[0], filename="、".join(dict.fromkeys(t["filename"] for t in turns)),
                              role_id=order[key], team_id=team["id"], team_name=team["name"],
                              character_name=role["character_name"], name_source=role["name_source"],
                              parsed={"turns": turns}))
    for i, group in enumerate(team["rounds"], 1):
        group = [dict(t, role_id=order[t["source_key"]],
                      character_name=identity.get(t["source_key"], {}).get("name"),
                      name_source=identity.get(t["source_key"], {}).get("name_source")) for t in group]
        start = min(t["started_at"] for t in group)
        end = max(t["settled_at"] for t in group) if all(t["settled_at"] for t in group) else None
        grades = sorted({t["grade"] for t in group})
        rounds.append({"number": i, "team_id": team["id"], "team_name": team["name"],
                       "started_at": start, "settled_at": end, "roles": group,
                       "seconds": int(seconds(end) - seconds(start)) if end else None,
                       "grade": " / ".join(grades), "luck_selected": any(t.get("reward_choice") == "碰碰运气" for t in group),
                       "incomplete": len(group) < 5 or not end})
    warnings = [f"仅识别到 {len(keys)} / 5 个角色的日志"] if len(keys) < 5 else []
    if team.get("uncertain"):
        warnings.append("同一时刻超过5份角色日志，无法仅凭时间区分队伍，暂单列保留收益")
    warnings.extend(dict.fromkeys(w for log in logs if log["source_key"] in keys for w in log["parsed"].get("warnings", [])))
    return {"id": team["id"], "name": team["name"], **context, "started_at": rounds[0]["started_at"],
            "logs": team_logs, "warnings": warnings,
            "summary": {"roles": sorted(roles, key=lambda r: r["role_id"]), "rounds": rounds,
                        "totals": rates(totals_for(roles, rounds))}}


def analyze_day(logs, saved_order):
    teams = [summarize_team(team, logs, saved_order) for team in split_teams(logs)]
    roles = [role for team in teams for role in team["summary"]["roles"]]
    rounds = [round_ for team in teams for round_ in team["summary"]["rounds"]]
    totals = totals_for(roles, rounds)
    totals["elapsed_seconds"] = sum(team["summary"]["totals"]["elapsed_seconds"] for team in teams)
    warnings = [f"{team['name']}：{w}" for team in teams for w in team["warnings"]]
    return {"teams": teams, "logs": [log for team in teams for log in team["logs"]],
            "summary": {"totals": rates(totals), "roles": roles, "rounds": rounds}, "warnings": warnings}
