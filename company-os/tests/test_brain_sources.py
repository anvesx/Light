"""Tests for the brain-era dummy data: source files, translations, lexicon, answer keys, new records, flight numbers."""
import email
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree

from company_data.generate_dummy_data import build
from company_data.simulated_today import TODAY

OLD_KEY_HASHES = {  # sha256 prefix of each pre-v2 answer key section, taken before F1 changed anything
    "finance_watch": "622540b9069f585d", "fraud_watch": "260f9675ad942663", "injection": "b0af4c15f03d29ff",
    "meeting_prep": "0f38150359be42cc", "project_risk": "d0ec36ad91baf7c1", "spend_advisor": "c4668b48ae34726a",
    "today": "61341b09a3c76a1d"}
REQUIRED_TOPICS = {"reminders", "insurance-claims", "payments", "launch-date", "timeline", "budget", "pricing",
                   "data-residency", "language-support", "lab-integration", "offline-mode", "gst-invoicing",
                   "gift-vouchers", "inventory-sync", "access-credentials", "reporting", "pilot", "support-sla",
                   "training", "compliance"}
KINDS = {"decision", "requirement", "blocker", "question", "commitment", "fact", "risk", "money", "sentiment"}
FLIGHT_NO = re.compile(r"^(KSA|SRG|NMB|TRG) \d{3}$")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def words(text):
    return re.findall(r"\w+", text.lower())


class BrainSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = build(os.path.join(cls.tmp, "a.db"), seed=42)
        cls.dir = os.path.join(cls.tmp, "brain_sources")
        with open(os.path.join(cls.tmp, "answer_keys.json")) as f:
            cls.keys = json.load(f)
        cls.brain = cls.keys["brain"]
        cls.conn = sqlite3.connect(cls.db)
        cls.conn.row_factory = sqlite3.Row
        cls.manifest = cls.load("manifest.json")["sources"]
        cls.translations = cls.load("translations.json")
        cls.lexicon = cls.load("topic_lexicon.json")["topics"]
        cls.cues = cls.load("kind_cues.json")
        cls.lines = {m["origin_ref"]: cls.read_lines(m) for m in cls.manifest}
        for call in ("LC01", "LC02"):
            with open(os.path.join(cls.dir, "live_calls", call + ".jsonl"), encoding="utf-8") as f:
                cls.lines[call] = [json.loads(x)["text"] for x in f]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp)

    @classmethod
    def load(cls, name):
        with open(os.path.join(cls.dir, name), encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def read_lines(cls, m):
        path = os.path.join(cls.dir, m["file"])
        if m["kind"] == "fathom":
            return [t["text"] for t in cls.load(m["file"])["transcript"]]
        if m["kind"] == "docx":
            with zipfile.ZipFile(path) as z:
                root = ElementTree.fromstring(z.read("word/document.xml"))
            return ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]
        if m["kind"] == "email":
            with open(path, "rb") as f:
                msg = email.message_from_bytes(f.read())
            return [x for x in msg.get_payload(decode=True).decode("utf-8").split("\n") if x.strip()]
        with open(path, encoding="utf-8") as f:
            return [re.match(r"^\[\d\d/\d\d/\d\d, \d\d:\d\d\] ([^:]+): (.+)$", x).group(2) for x in f.read().splitlines()]

    def clean(self, ref, n):
        """The clean English of a line: its translation, or the raw text when the line is English."""
        return self.translations.get(f"{ref}:{n}", self.lines[ref][n - 1])

    def topics_in(self, text):
        w = set(words(text))
        return {t for t, v in self.lexicon.items() if w & set(v["en"])}

    def kinds_in(self, text):
        low = text.lower()
        return {k for k, cues in self.cues.items() if any(c in low for c in cues)}

    def entries(self):
        return {e["origin_ref"]: e for e in self.brain["sources"]}

    # ---- old data stays the same ------------------------------------------------------------------
    def test_old_answer_key_sections_are_unchanged(self):
        for section, digest in OLD_KEY_HASHES.items():
            got = hashlib.sha256(json.dumps(self.keys[section], sort_keys=True).encode()).hexdigest()[:16]
            self.assertEqual(got, digest, section)
        self.assertEqual(set(self.keys), set(OLD_KEY_HASHES) | {"brain"})

    def test_same_seed_gives_same_sources(self):
        other = build(os.path.join(self.tmp, "b.db"), seed=42)
        self.assertTrue(other)
        with open(os.path.join(self.tmp, "answer_keys.json")) as f:
            self.assertEqual(json.load(f)["brain"], self.brain)

    # ---- files ------------------------------------------------------------------------------------
    def test_manifest_counts_and_shapes(self):
        self.assertGreaterEqual(len(self.manifest), 25)
        self.assertEqual({m["kind"] for m in self.manifest}, {"fathom", "docx", "email", "chat"})
        for m in self.manifest:
            self.assertTrue(os.path.exists(os.path.join(self.dir, m["file"])), m["file"])
            self.assertRegex(m["arrives_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d$")
            self.assertIn(m["hint_area"], [None] + [f"C{n:02d}" for n in range(1, 11)])
        self.assertEqual({m["origin_ref"] for m in self.manifest if not m["history"]}, {"SRC29", "SRC30", "SRC31"})
        for m in self.manifest:
            if not m["history"]:
                self.assertGreaterEqual(m["arrives_at"], TODAY)
            else:
                self.assertLess(m["arrives_at"], TODAY)

    def test_fathom_files_have_the_api_shape(self):
        for m in self.manifest:
            if m["kind"] != "fathom":
                continue
            f = self.load(m["file"])
            self.assertIsInstance(f["recording_id"], int)
            self.assertTrue(f["title"] and f["created_at"].endswith("Z"))
            emails = {i["email"] for i in f["calendar_invitees"]}
            self.assertGreaterEqual(len(emails), 2)
            last = -1
            for t in f["transcript"]:
                h, mi, s = map(int, t["timestamp"].split(":"))
                self.assertGreater(h * 3600 + mi * 60 + s, last)
                last = h * 3600 + mi * 60 + s
                self.assertIn(t["speaker"]["matched_calendar_invitee_email"], emails | {None})
                self.assertTrue(t["text"])

    def test_docx_email_chat_files_parse(self):
        kinds = {m["kind"]: m for m in self.manifest}
        for m in self.manifest:
            if m["kind"] == "docx":
                with zipfile.ZipFile(os.path.join(self.dir, m["file"])) as z:
                    self.assertIn("word/document.xml", z.namelist())
            if m["kind"] == "email":
                with open(os.path.join(self.dir, m["file"]), "rb") as f:
                    msg = email.message_from_bytes(f.read())
                self.assertTrue(msg["From"] and msg["To"] and msg["Subject"] and msg["Date"])
        self.assertEqual(set(kinds), {"fathom", "docx", "email", "chat"})

    def test_live_calls_have_the_shape(self):
        for call in ("LC01", "LC02"):
            with open(os.path.join(self.dir, "live_calls", call + ".jsonl"), encoding="utf-8") as f:
                rows = [json.loads(x) for x in f]
            self.assertGreaterEqual(len(rows), 8)
            for i, r in enumerate(rows, 1):
                self.assertEqual(list(r), ["line_no", "t_sec", "speaker", "speaker_id", "lang", "text"])
                self.assertEqual(r["line_no"], i)
                self.assertIn(r["lang"], ("en", "hi", "hinglish"))
                if r["lang"] != "en":
                    self.assertIn(f"{call}:{i}", self.translations)
            self.assertEqual([r["t_sec"] for r in rows], sorted(r["t_sec"] for r in rows))

    def test_every_non_english_line_is_translated_except_the_review_lines(self):
        review = {(e["origin_ref"], n) for e in self.brain["sources"] for n in e["review_lines"]}
        self.assertEqual(len(review), 2)
        for ref, lines in self.lines.items():
            for n, text in enumerate(lines, 1):
                english = text.isascii() and not re.search(r"\b(haan|hai|hum|nahi|kya|toh|aur|ek|thik|theek|matlab)\b", text.lower())
                if (ref, n) in review:
                    self.assertNotIn(f"{ref}:{n}", self.translations)
                elif not english:
                    self.assertIn(f"{ref}:{n}", self.translations, (ref, n, text))
        for k in self.translations:
            ref, n = k.split(":")
            self.assertLessEqual(int(n), len(self.lines[ref]), k)
        self.assertTrue(any(re.search("[\u0900-\u097f]", t) for lines in self.lines.values() for t in lines))

    # ---- lexicon and cues ---------------------------------------------------------------------------
    def test_lexicon_has_required_topics_and_shape(self):
        self.assertLessEqual(REQUIRED_TOPICS, set(self.lexicon))
        for topic, v in self.lexicon.items():
            self.assertEqual(set(v), {"en", "hinglish", "hi", "label"}, topic)
            for lang in ("en", "hinglish", "hi"):
                self.assertTrue(v[lang], (topic, lang))
            self.assertTrue(all(w == w.lower() and " " not in w for w in v["en"] + v["hinglish"]), topic)

    def test_every_key_topic_is_in_the_lexicon(self):
        b = self.brain
        topics = {i["topic"] for e in b["sources"] for i in e["items"]}
        topics |= {t for p in b["playbooks"] for k in ("later_changed_topics", "went_right_topics", "went_wrong_topics") for t in p[k]}
        topics |= {t for d in b["deals"] for k in ("kickoff_topics", "objection_topics") for t in d[k]}
        topics |= {x["topic"] for c in b["live_calls"] for x in c["expected"]}
        self.assertLessEqual(topics, set(self.lexicon))

    # ---- answer keys ----------------------------------------------------------------------------------
    def test_every_item_points_at_the_exact_line(self):
        n_items = 0
        for e in self.brain["sources"]:
            ref, seen = e["origin_ref"], set()
            keyed = set()
            for it in e["items"]:
                n_items += 1
                self.assertNotIn(it["key"], seen)
                seen.add(it["key"])
                self.assertIn(it["kind"], KINDS)
                self.assertEqual(it["line_from"], it["line_to"])
                n = it["line_from"]
                self.assertTrue(1 <= n <= len(self.lines[ref]), it["key"])
                keyed.add(n)
                text = self.clean(ref, n)
                for w in it["must_contain"]:
                    self.assertIn(w, text.lower(), it["key"])
                self.assertEqual(self.topics_in(text), {it["topic"]}, (it["key"], text))
                want = set() if it["kind"] == "fact" else {it["kind"]}
                self.assertEqual(self.kinds_in(text), want, (it["key"], text))
            for n in range(1, len(self.lines[ref]) + 1):  # a line with no key must not look like an item
                if n not in keyed and n not in e["review_lines"]:
                    text = self.clean(ref, n)
                    self.assertEqual(self.topics_in(text), set(), (ref, n, text))
        self.assertGreaterEqual(n_items, 60)

    def test_every_kind_appears_and_languages_are_mixed(self):
        kinds = {i["kind"] for e in self.brain["sources"] for i in e["items"]}
        self.assertEqual(kinds, KINDS)
        self.assertLessEqual({"en", "hinglish", "mixed"}, {e["language"] for e in self.brain["sources"]})

    def test_links_and_duplicates_point_at_real_items(self):
        keys = {i["key"]: (e["origin_ref"], i) for e in self.brain["sources"] for i in e["items"]}
        links = [l for e in self.brain["sources"] for l in e["links"]]
        for l in links:
            self.assertIn(l["from"], keys)
            self.assertIn(l["to"], keys)
            self.assertIn(l["rel"], {"supersedes", "answers", "refines", "follows_up", "about", "contradicts"})
        self.assertEqual(sum(l["rel"] == "supersedes" for l in links), 3)
        self.assertEqual(sum(l["rel"] == "contradicts" for l in links), 2)
        for a, b in self.brain["duplicates"]:
            self.assertEqual(keys[a][1]["topic"], keys[b][1]["topic"])
            self.assertEqual(keys[a][1]["kind"], keys[b][1]["kind"])
            self.assertNotEqual(keys[a][0], keys[b][0])
        self.assertEqual(len(self.brain["duplicates"]), 2)

    def test_special_cases_are_planted(self):
        e = self.entries()
        self.assertEqual(len(e["SRC29"]["items"]), 2)
        self.assertEqual(e["SRC29"]["expected_route"], "hold")
        self.assertEqual(sum(len(x["review_lines"]) for x in e.values()), 2)
        inj = [x for x in e.values() if x["injection_lines"]]
        self.assertEqual(len(inj), 1)
        n = inj[0]["injection_lines"][0]
        self.assertIn("outside@example.com", self.lines[inj[0]["origin_ref"]][n - 1])
        wa = next(i for i in e["SRC25"]["items"] if i["kind"] == "decision" and i["topic"] == "reminders")
        self.assertEqual(wa["line_from"], 14)  # the plan names source line 14 for the WhatsApp decision

    def test_playbooks_deals_live_calls_and_brief(self):
        b = self.brain
        self.assertEqual([(p["area_id"], p["deal_id"], p["outcome"]) for p in b["playbooks"]],
                         [("C04", "L05", "won"), ("C01", "L01", "won"), ("C09", "L22", "lost"), ("C10", "L23", "lost")])
        for p in b["playbooks"]:
            lead = self.conn.execute("SELECT client_id, stage FROM leads WHERE lead_id=?", (p["deal_id"],)).fetchone()
            self.assertEqual((lead["client_id"], lead["stage"]), (p["area_id"], p["outcome"]))
        self.assertEqual({d["deal_id"]: d["similar_top2"] for d in b["deals"]}, {"L20": ["C04", "C09"], "L21": ["C01", "C10"]})
        self.assertEqual([c["call_id"] for c in b["live_calls"]], ["LC01", "LC02"])
        for c in b["live_calls"]:
            self.assertEqual(c["window_lines"], 2)
            for x in c["expected"]:
                self.assertIn(x["topic"], self.topics_in(self.clean(c["call_id"], x["line_no"])), x)
        lc2 = b["live_calls"][1]["expected"][0]
        self.assertEqual(lc2["kind"], "contradiction")
        wa = next(i for i in self.entries()["SRC25"]["items"] if i["kind"] == "decision" and i["topic"] == "reminders")
        self.assertEqual(lc2["against"], wa["key"])
        brief = b["project_brief"][0]
        ev = self.conn.execute("SELECT * FROM calendar_events WHERE event_id=?", (brief["event_id"],)).fetchone()
        self.assertEqual((ev["client_id"], ev["project_id"]), ("C04", "PR05"))
        allkeys = {i["key"] for e in b["sources"] for i in e["items"]}
        self.assertLessEqual(set(brief["must_cite_keys"]), allkeys)

    # ---- new records ------------------------------------------------------------------------------
    def test_cast_ids_exist_with_the_right_status_and_owner(self):
        q = lambda sql, *a: [dict(r) for r in self.conn.execute(sql, a)]
        want = {"C07": ("prospect", "P03", "L20", "negotiation"), "C08": ("prospect", "P03", "L21", "proposal"),
                "C09": ("lost", "P04", "L22", "lost"), "C10": ("lost", "P30", "L23", "lost")}
        for cid, (status, owner, lead, stage) in want.items():
            c = q("SELECT * FROM clients WHERE client_id=?", cid)[0]
            self.assertEqual((c["status"], c["account_manager_id"]), (status, owner))
            l = q("SELECT * FROM leads WHERE lead_id=?", lead)[0]
            self.assertEqual((l["client_id"], l["owner_id"], l["stage"]), (cid, owner, stage))
            self.assertGreaterEqual(len(q("SELECT 1 FROM people WHERE client_id=?", cid)), 2)
            self.assertGreaterEqual(len(q("SELECT 1 FROM growth_calls WHERE lead_id=?", lead)), 2)
        self.assertTrue(all(q("SELECT lost_reason FROM leads WHERE lead_id=?", x)[0]["lost_reason"] for x in ("L22", "L23")))
        self.assertEqual([r["person_id"] for r in q("SELECT person_id FROM people WHERE client_id IN ('C07','C08','C09','C10') ORDER BY 1")],
                         [f"X{n}" for n in range(13, 21)])
        names = {r["person_id"]: r["name"] for r in q("SELECT person_id, name FROM people WHERE person_id IN ('P01','P03','P05')")}
        self.assertEqual(names, {"P01": "Ammar Khan", "P03": "Anthony Fernandes", "P05": "Akbar Ali"})
        self.assertEqual(q("SELECT csm_id FROM clients WHERE client_id IN ('C01','C04','C06')")[0]["csm_id"], "P05")
        self.assertEqual(q("SELECT lead_id FROM projects WHERE project_id='PR05'")[0]["lead_id"], "P09")

    def test_invoices_cover_each_won_project_month_by_month(self):
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM client_invoices")]
        self.assertGreater(len(rows), 30)
        for p in self.conn.execute("SELECT project_id, client_id, start_on FROM projects"):
            months = sorted(r["month"] for r in rows if r["project_id"] == p["project_id"])
            self.assertEqual(months[0], p["start_on"][:7])
            self.assertEqual(len(months), len(set(months)))
            self.assertLessEqual(months[-1], TODAY[:7])
        self.assertTrue({r["status"] for r in rows} <= {"paid", "sent", "overdue"})
        self.assertTrue(all(r["amount_inr"] > 0 for r in rows))

    def test_pr05_has_an_event_in_the_next_24_hours(self):
        start = datetime.fromisoformat(TODAY + "T09:00")
        rows = self.conn.execute("SELECT start_at FROM calendar_events WHERE project_id='PR05'").fetchall()
        self.assertTrue(any(start < datetime.fromisoformat(r[0]) <= start + timedelta(hours=24) for r in rows))
        self.assertTrue(self.conn.execute("SELECT 1 FROM calendar_events WHERE client_id='C07'").fetchone())

    def test_every_flight_has_a_number_in_the_c9_format(self):
        for table in ("trips", "fare_options"):
            for r in self.conn.execute(f"SELECT * FROM {table}"):
                if r["mode"] == "flight":
                    self.assertRegex(r["flight_no"], FLIGHT_NO, (table, r[0]))
                else:
                    self.assertIsNone(r["flight_no"])
        for r in self.conn.execute("SELECT option_id, carrier, flight_no FROM fare_options WHERE flight_no IS NOT NULL"):
            h = 100 + int(hashlib.sha1(r["option_id"].encode()).hexdigest(), 16) % 900
            self.assertEqual(r["flight_no"].split()[1], str(h))
        for r in self.conn.execute("SELECT * FROM trips WHERE mode='flight'"):
            self.assertTrue(re.match(r"^\d\d:\d\d$", r["depart_time"]))
            paid = self.conn.execute("SELECT 1 FROM fare_options WHERE trip_id=? AND flight_no=? AND depart_time=?",
                                     (r["trip_id"], r["flight_no"], r["depart_time"])).fetchone()
            self.assertTrue(paid, r["trip_id"])
        self.assertTrue(all(re.match(r"^\d\d:\d\d$", r[0]) for r in self.conn.execute("SELECT arrive_time FROM fare_options")))


if __name__ == "__main__":
    unittest.main()
