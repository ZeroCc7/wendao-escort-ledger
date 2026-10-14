"""Read local chat logs and persist numbered escort records on this computer."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from desktop.escort_parser import (
    date_from_filename,
    fingerprint,
    split_log_by_date,
)
from desktop.escort_analysis import ANALYSIS_VERSION, analyze_day, parse_desktop_log


MAX_LOG_BYTES = 5 * 1024 * 1024
ROLE_PREFIX = re.compile(r"^(.+?)_押镖日志(?:_|$)")
DATE_SUFFIX = re.compile(r"(?:[_-]?20\d{6}(?:\d{3})?)$")


def default_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    return (Path(root) if root else Path.home() / "AppData" / "Local") / "WendaoEscort"


def role_key(path: Path) -> str:
    match = ROLE_PREFIX.match(path.stem)
    return (match.group(1) if match else DATE_SUFFIX.sub("", path.stem)) or path.stem


def is_snapshot(shorter: list[dict], longer: list[dict]) -> bool:
    if not shorter or len(shorter) > len(longer):
        return False
    if shorter == longer[:len(shorter)]:
        return True
    return (not shorter[-1]["settled_at"]
            and shorter[:-1] == longer[:len(shorter) - 1]
            and all(shorter[-1][key] == longer[len(shorter) - 1][key]
                    for key in ("started_at", "grade", "deposit")))


@dataclass
class ScanResult:
    scanned: int
    saved: int
    skipped: int
    warnings: list[str]
    dates: list[str]


class LocalEscortStore:
    def __init__(self, database: Path | None = None):
        self.database = database or default_data_dir() / "escort.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS roles (
                    source_key TEXT PRIMARY KEY, role_id INTEGER NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS logs (
                    path TEXT NOT NULL, day TEXT NOT NULL, source_key TEXT NOT NULL,
                    filename TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    parsed TEXT NOT NULL, modified_at TEXT NOT NULL,
                    PRIMARY KEY(path, day)
                );
                CREATE INDEX IF NOT EXISTS logs_day ON logs(day);
                CREATE TABLE IF NOT EXISTS team_roles (
                    day TEXT NOT NULL, team_id TEXT NOT NULL, source_key TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY(day, team_id, source_key)
                );
                """
            )

    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        return db

    def setting(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self.connect() as db:
            db.execute(
                "INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def set_role(self, key: str, role_id: int, day: str, team_id: str):
        team = next((team for team in self.day(day)["teams"] if team["id"] == team_id), None)
        if not team or key not in {log["source_key"] for log in team["logs"]}:
            raise ValueError("队伍记录已变化，请刷新后重试")
        if not 1 <= role_id <= len(team["logs"]):
            raise ValueError(f"请输入 1 至 {len(team['logs'])} 的队内编号")
        order = {log["source_key"]: log["role_id"] for log in team["logs"]}
        current = order[key]
        other = next(source for source, number in order.items() if number == role_id)
        order[key], order[other] = role_id, current
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO team_roles VALUES (?, ?, ?, ?)",
                           [(day, team_id, source, number) for source, number in order.items()])

    def scan(self, game_dir: Path) -> ScanResult:
        chat = game_dir if game_dir.name.lower() == "chat" else game_dir / "chat"
        if not chat.is_dir():
            raise ValueError(f"未找到日志目录：{chat}")
        paths = sorted(p for p in chat.rglob("*.txt") if p.is_file())
        scanned = saved = skipped = 0
        warnings: list[str] = []
        dates: set[str] = set()
        with self.connect() as db:
            for path in paths:
                scanned += 1
                try:
                    if path.stat().st_size > MAX_LOG_BYTES:
                        raise ValueError("文件超过 5 MB")
                    raw = path.read_bytes()
                    if not raw:
                        raise ValueError("空文件")
                    try:
                        first_day = date_from_filename(path.name)
                    except ValueError:
                        first_day = datetime.fromtimestamp(path.stat().st_mtime).date()
                        warnings.append(f"{path.name}：文件名无日期，暂用文件修改日期 {first_day}")
                    days = split_log_by_date(raw, first_day)
                    if not days:
                        skipped += 1
                        continue
                    parsed_days = []
                    for day, day_raw in days.items():
                        try:
                            parsed_days.append((day, day_raw, parse_desktop_log(day_raw, day)))
                        except ValueError as exc:
                            if "未找到可识别的押镖轮次" not in str(exc):
                                raise
                    if not parsed_days:
                        skipped += 1
                        continue
                    key = str(path.parent.resolve()) + "|" + role_key(path)
                    for day, day_raw, parsed in parsed_days:
                        day_text = day.isoformat()
                        db.execute(
                            """INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(path, day) DO UPDATE SET
                              source_key=excluded.source_key,
                              filename=excluded.filename,
                              fingerprint=excluded.fingerprint,
                              parsed=excluded.parsed,
                              modified_at=excluded.modified_at""",
                            (
                                str(path.resolve()), day_text, key, path.name,
                                fingerprint(day_raw), json.dumps(parsed, ensure_ascii=False),
                                datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                            ),
                        )
                        dates.add(day_text)
                        saved += 1
                except (OSError, ValueError) as exc:
                    skipped += 1
                    warnings.append(f"{path.name}：{exc}")
        return ScanResult(scanned, saved, skipped, warnings, sorted(dates, reverse=True))

    def days(self) -> list[str]:
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT DISTINCT day FROM logs ORDER BY day DESC")]

    def day(self, day: str) -> dict:
        date.fromisoformat(day)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM logs WHERE day=? ORDER BY path",
                (day,),
            ).fetchall()
            saved_order = {}
            for row in db.execute("SELECT * FROM team_roles WHERE day=?", (day,)):
                saved_order.setdefault(row["team_id"], {})[row["source_key"]] = row["role_id"]
        logs, seen = [], set()
        warnings = []
        for row in rows:
            parsed = json.loads(row["parsed"])
            path = Path(row["path"])
            key = str(path.parent.resolve()) + "|" + role_key(path)
            if parsed.get("desktop_analysis_version") != ANALYSIS_VERSION:
                try:
                    if path.stat().st_size > MAX_LOG_BYTES:
                        raise ValueError("文件超过 5 MB")
                    try:
                        first = date_from_filename(path.name)
                    except ValueError:
                        first = datetime.fromtimestamp(path.stat().st_mtime).date()
                    raw = split_log_by_date(path.read_bytes(), first)[date.fromisoformat(day)]
                    parsed = parse_desktop_log(raw, date.fromisoformat(day))
                    with self.connect() as db:
                        db.execute("UPDATE logs SET parsed=?, source_key=? WHERE path=? AND day=?",
                                   (json.dumps(parsed, ensure_ascii=False), key, row["path"], day))
                except (OSError, ValueError, KeyError):
                    warnings.append(f"{row['filename']}：原日志不可用，碰碰运气结果待重新扫描；保留原有收益")
            if row["fingerprint"] in seen:
                if not re.fullmatch(r"20\d{9}", Path(row["filename"]).stem):
                    warnings.append(f"{row['filename']}：内容重复，未重复统计")
                continue
            seen.add(row["fingerprint"])
            logs.append({
                "filename": row["filename"], "path": row["path"],
                "source_key": key, "parsed": parsed,
            })
        # The game's numbered files can be incremental snapshots of a named
        # character log. Keep the longest record and avoid counting copies as
        # additional team members.
        logs = [log for log in logs if not (
            re.fullmatch(r"20\d{9}", Path(log["filename"]).stem)
            and any(other is not log
                    and is_snapshot(log["parsed"]["turns"], other["parsed"]["turns"])
                    for other in logs)
        )]
        # A named source may span several files; repeated turns in those files
        # must not count as another member or another payout.
        seen_turns = set()
        for log in logs:
            unique = []
            for turn in log["parsed"]["turns"]:
                signature = (log["source_key"], json.dumps(turn, sort_keys=True))
                if signature not in seen_turns:
                    unique.append(turn)
                    seen_turns.add(signature)
            log["parsed"]["turns"] = unique
        result = analyze_day([log for log in logs if log["parsed"]["turns"]], saved_order)
        result["warnings"] = warnings + result["warnings"]
        return {"date": day, **result}

    def history(self) -> list[dict]:
        result = []
        for day in self.days():
            data = self.day(day)
            totals = data["summary"]["totals"] if data["summary"] else {}
            grades = {"A级镖": 0, "B级镖": 0, "C级镖": 0, "未知镖级": 0}
            for round_ in data["summary"]["rounds"] if data["summary"] else []:
                if round_["settled_at"]:
                    grade = round_["grade"] if round_["grade"] in grades else "未知镖级"
                    grades[grade] += 1
            result.append({"date": day, "roles": len(data["logs"]), "teams": len(data["teams"]),
                           **totals, "grade_counts": grades})
        return result
