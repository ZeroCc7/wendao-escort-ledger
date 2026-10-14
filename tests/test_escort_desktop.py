"""Desktop team boundaries, local numbering, luck accounting and saved-history upgrade."""
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from desktop.escort_data import LocalEscortStore
from desktop.escort_analysis import parse_desktop_log
from desktop.escort_parser import parse_log


def log(start="20:00:00", end="20:04:00", reward=100, deposit=159600,
        choice="普通收益", result="", tag=""):
    return (f"{tag}\n#W{start}#n你提交了#G{deposit}#n文游戏币#n作为押金\n"
            f"#W{end}#n队伍选择获得#R{choice}#n{result}\n"
            f"#W{end}#n你获得了#G{deposit}#n文游戏币#n。\n"
            f"#W{end}#n你获得了#cFF00FF{reward}#n文游戏币\n").encode()


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chat = self.root / "game/chat"
        self.chat.mkdir(parents=True)
        self.store = LocalEscortStore(self.root / "ledger.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, raw):
        path = self.chat / (name + "_20261006000.txt")
        path.write_bytes(raw)
        return path

    def scan(self):
        self.store.scan(self.chat)
        return self.store.day("2026-10-06")

    def test_two_teams_have_independent_numbers_and_accounting(self):
        for team in range(2):
            for member in range(5):
                self.write(f"t{team}-m{member}", log(f"{20+team}:00:0{member}", f"{20+team}:04:0{member}",
                           reward=100+member, deposit=159600+member*1050, tag=f"{team}/{member}"))
        day = self.scan()
        self.assertEqual(len(day["teams"]), 2)
        self.assertEqual(day["summary"]["totals"]["completed_rounds"], 2)
        self.assertEqual(day["summary"]["totals"]["coins"], 1020)
        self.assertEqual(day["summary"]["totals"]["elapsed_seconds"], 488)
        self.assertEqual(sum(self.store.history()[0]["grade_counts"].values()), 2)
        for team in day["teams"]:
            self.assertEqual(sorted(l["role_id"] for l in team["logs"]), [1, 2, 3, 4, 5])
        first, second = day["teams"]
        key = first["logs"][0]["source_key"]
        self.store.set_role(key, 5, day["date"], first["id"])
        again = self.store.day(day["date"])
        self.assertEqual(next(l["role_id"] for l in again["teams"][0]["logs"] if l["source_key"] == key), 5)
        self.assertEqual(again["teams"][1]["logs"], second["logs"])
        with self.assertRaises(ValueError):
            self.store.set_role(key, 6, day["date"], first["id"])

    def test_concurrent_teams_separate_by_settlement(self):
        for team in range(2):
            for member in range(5):
                self.write(f"t{team}-m{member}", log(end=f"20:0{4+team}:00", reward=member+team+1))
        self.assertEqual(len(self.scan()["teams"]), 2)

    def test_one_log_can_participate_in_two_different_teams(self):
        self.write("shared", log() + log("21:00:00", "21:04:00"))
        for i in range(4):
            self.write(f"early{i}", log(tag=f"early{i}"))
            self.write(f"late{i}", log("21:00:00", "21:04:00", tag=f"late{i}"))
        day = self.scan()
        self.assertEqual([len(t["logs"]) for t in day["teams"]], [5, 5])
        self.assertEqual(day["summary"]["totals"]["coins"], 1000)

    def test_luck_counts_choice_not_blessings_and_never_multiplies_money(self):
        raw = (log(choice="碰碰运气", result="，你获得了#R10倍#n收益。", reward=1000)
               + log("20:05:00", "20:09:00", choice="碰碰运气", result="，你获得了移速祝福。", reward=0)
               + log("20:10:00", "20:14:00", choice="碰碰运气", result="，你获得了#R1.2倍#n收益。", reward=120)
               + log("20:15:00", "20:19:00", reward=100))
        parsed = parse_desktop_log(raw, date(2026, 10, 6))
        self.assertEqual([t["reward_multiplier"] for t in parsed["turns"]], [10, None, 1.2, None])
        self.assertEqual(parsed["turns"][1]["luck_result"], "移速祝福")
        self.write("role", raw)
        totals = self.scan()["summary"]["totals"]
        self.assertEqual((totals["luck_count"], totals["luck_rounds"], totals["coins"]), (3, 3, 1220))

    def test_existing_history_reparses_and_discards_global_number(self):
        path = self.write("role", log(choice="碰碰运气", result="，你获得了#R2倍#n收益。"))
        self.scan()
        old = parse_log(path.read_bytes(), date(2026, 10, 6))
        with self.store.connect() as db:
            db.execute("UPDATE logs SET parsed=?", (json.dumps(old),))
            db.execute("INSERT INTO roles VALUES ('legacy', 27)")
        day = LocalEscortStore(self.store.database).day("2026-10-06")
        self.assertEqual(day["logs"][0]["role_id"], 1)
        self.assertEqual(day["summary"]["totals"]["luck_count"], 1)

    def test_duplicate_files_and_repeat_scan_do_not_duplicate_money(self):
        self.write("one", log())
        self.write("copy", log())
        first = self.scan()
        second = self.scan()
        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(first["summary"]["totals"]["coins"], 100)

    def test_numbered_incremental_snapshot_is_not_another_role(self):
        full = log() + log("20:05:00", "20:09:00", reward=200)
        partial = log() + "#W20:05:00#n你提交了#G159600#n文游戏币#n作为押金\n".encode()
        (self.chat / "20261006000.txt").write_bytes(partial)
        self.write("named", full)
        day = self.scan()
        self.assertEqual(len(day["logs"]), 1)
        self.assertEqual(day["summary"]["totals"]["coins"], 300)

    def test_missing_member_keeps_numbers_bounded(self):
        for i in range(3):
            self.write(f"m{i}", log(tag=str(i)))
        day = self.scan()
        self.assertEqual([r["role_id"] for r in day["summary"]["roles"]], [1, 2, 3])
        self.assertTrue(day["warnings"])

    def test_names_need_consistent_roster_and_join_evidence(self):
        names = ["甲", "乙", "丙", "丁", "戊"]
        roster = "#W19:00:00#n由于你队伍中的" + "、".join(f"#Y{name}#n" for name in names) + "为#@年费会员|Open:YearInsiderDlg#@，你获得奖励。\n"
        for i, name in enumerate(names):
            joins = "" if i == 4 else "".join(
                f"#W19:30:0{j}#n#Y#<{other}#>#n加入了队伍。\n"
                for j, other in enumerate(names) if other != name
            )
            leader = "#W19:29:00#n你加入#Y#<甲#>#n的队伍。\n" if i == 1 else ""
            server = "#W18:00:00#n你在#Y【雪山飞狐】一线#n上线啦！\n" if i == 0 else ""
            self.write(f"m{i}", (server + roster + leader + joins).encode() + log(tag=name))
        day = self.scan()
        found = {r["character_name"]: r["name_source"] for r in day["summary"]["roles"]}
        self.assertEqual(set(found), set(names))
        self.assertEqual(found["戊"], "队伍排除")
        self.assertEqual(sum(source == "入队记录" for source in found.values()), 4)
        self.assertEqual(day["teams"][0]["leader_name"], "甲")
        self.assertEqual(day["teams"][0]["server_name"], "雪山飞狐")

    def test_conflicting_rosters_do_not_assign_names(self):
        roster = lambda names: ("#W19:00:00#n由于你队伍中的"
                                + "、".join(f"#Y{name}#n" for name in names)
                                + "为#@年费会员|Open:YearInsiderDlg#@。\n").encode()
        for i in range(5):
            names = ["甲", "乙", "丙", "丁", "戊" if i < 4 else "己"]
            joins = "".join(f"#W19:30:0{j}#n#Y#<{name}#>#n加入了队伍。\n"
                            for j, name in enumerate(names) if j != i).encode()
            self.write(f"m{i}", roster(names) + joins + log(tag=str(i)))
        self.assertTrue(all(r["character_name"] is None for r in self.scan()["summary"]["roles"]))

    def test_extra_rewards_consumption_and_estimated_level(self):
        raw = ("#W20:00:00#n你提交了#G159600#n文游戏币#n作为押金\n"
               "#W20:01:00#n由于你击退了瓢把子，获得了#R特级血玲珑#n的奖励。\n"
               "#W20:02:00#n你使用了12个药品以恢复法力状态。\n"
               "#W20:02:01#n你消耗了#R4#n点八卦神符耐久度进行传送。\n"
               "#W20:04:00#n你获得了#G159600#n文游戏币#n。\n"
               "#W20:04:00#n你获得了#cFF00FF100#n文游戏币#n。\n"
               "#W20:04:00#n救助灾民，你的#R声望值#n增加了#R1#n点！\n").encode()
        self.write("m0", raw)
        day = self.scan()
        turn = day["summary"]["rounds"][0]["roles"][0]
        role = day["summary"]["roles"][0]
        self.assertEqual((turn["reputation"], turn["medicine_count"], turn["talisman_durability"]), (1, 12, 4))
        self.assertEqual(turn["pirate_rewards"][0]["reward"], "特级血玲珑")
        self.assertEqual((role["level_estimate"], role["pirate_reward_count"], role["coins"]), (152, 1, 100))


if __name__ == "__main__":
    unittest.main()
