"""Brain inbox: each reader on a small sample, the router, language, topic lexicon and receive()."""
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from email.message import EmailMessage

from control_plane.company_brain import BrainStore, inbox
from control_plane.company_brain.area_router import route
from control_plane.company_brain.inbox import should_ingest
from control_plane.company_brain.language import detect_language
from control_plane.company_brain.source_readers import read_chat, read_docx, read_eml, read_fathom_json, read_plain
from control_plane.company_brain.topic_lexicon import load_lexicon, topics_in
from control_plane.company_memory import MemoryStore

FATHOM = json.dumps({
    "recording_id": 4711, "title": "Patient Booking App sync", "created_at": "2026-10-02T10:30:00Z",
    "calendar_invitees": [{"name": "Dr Rao", "email": "Rao@MedBridge.example"}, {"name": "Akbar Ali", "email": "akbar@devx.example"}],
    "transcript": [
        {"speaker": {"display_name": "Dr Rao", "matched_calendar_invitee_email": "rao@medbridge.example"},
         "text": "Reminders WhatsApp pe chahiye.", "timestamp": "00:00:05"},
        {"speaker": {"display_name": "Akbar Ali", "matched_calendar_invitee_email": None}, "text": "Theek hai.", "timestamp": "00:01:10"}]})
CHAT = "[02/10/26, 10:15] Dr Rao: Insurance claim upload\nchahiye\n[02/10/26, 10:16] Akbar Ali: Ok, noted\n"


def make_docx(paragraphs, title="Scope note"):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    core = (f'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
            f'<dc:title>{title}</dc:title><dcterms:created>2026-10-03T09:00:00Z</dcterms:created></cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


def make_eml():
    msg = EmailMessage()
    msg["From"] = "Rhea Kulkarni <rhea.kulkarni@tailorbird.example>"
    msg["To"] = "akbar@devx.example"
    msg["Subject"] = "Offline billing"
    msg["Date"] = "Fri, 02 Oct 2026 11:00:00 +0530"
    msg["Message-ID"] = "<abc@tailorbird.example>"
    msg.set_content("Offline billing must work.\n\nGST invoice format is fixed.\n")
    return msg.as_bytes()


def make_data():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE clients (client_id TEXT, name TEXT);
        CREATE TABLE people (person_id TEXT, name TEXT, email TEXT, is_devx INTEGER, client_id TEXT);
        CREATE TABLE projects (project_id TEXT, client_id TEXT, name TEXT);
        CREATE TABLE calendar_events (event_id TEXT, title TEXT, client_id TEXT);
        INSERT INTO clients VALUES ('C01','Tailorbird Menswear'),('C04','MedBridge Clinics'),('C07','CareNest Clinics');
        INSERT INTO calendar_events VALUES ('E1','Quarterly review with the Orbit team','C07'),('E2','DevX delivery review',NULL);
        INSERT INTO people VALUES ('X20','Anil','anil@carenest.example',0,'C07');
        INSERT INTO people VALUES ('X01','Rhea Kulkarni','rhea.kulkarni@tailorbird.example',0,'C01'),
            ('X09','Dr Rao','rao@medbridge.example',0,'C04'),('P05','Akbar Ali','akbar@devx.example',1,NULL);
        INSERT INTO projects VALUES ('PR05','C04','Patient Booking App'),('PR01','C01','POS Rollout');
    """)
    return conn


class TestReaders(unittest.TestCase):
    def test_fathom(self):
        meta, lines = read_fathom_json(FATHOM)
        self.assertEqual((meta["title"], meta["occurred_at"], meta["origin_ref"]), ("Patient Booking App sync", "2026-10-02T10:30", "4711"))
        self.assertEqual([(l["line_no"], l["speaker"], l["t_sec"]) for l in lines], [(1, "Dr Rao", 5), (2, "Akbar Ali", 70)])
        self.assertIn("rao@medbridge.example", {p["email"] for p in meta["participants"]})

    def test_docx(self):
        meta, lines = read_docx(make_docx(["Scope note", "", "Contact: rao@medbridge.example", "We need Hindi screens."]))
        self.assertEqual((meta["title"], meta["occurred_at"]), ("Scope note", "2026-10-03T09:00"))
        self.assertEqual([l["text"] for l in lines], ["Scope note", "Contact: rao@medbridge.example", "We need Hindi screens."])
        self.assertEqual(meta["participants"], [{"name": "", "email": "rao@medbridge.example"}])

    def test_eml(self):
        meta, lines = read_eml(make_eml())
        self.assertEqual((meta["title"], meta["occurred_at"]), ("Offline billing", "2026-10-02T11:00"))
        self.assertEqual([l["text"] for l in lines], ["Offline billing must work.", "GST invoice format is fixed."])
        self.assertEqual(lines[0]["speaker"], "Rhea Kulkarni")
        self.assertIn("rhea.kulkarni@tailorbird.example", {p["email"] for p in meta["participants"]})

    def test_chat_joins_continuation_lines(self):
        meta, lines = read_chat(CHAT)
        self.assertEqual([l["text"] for l in lines], ["Insurance claim upload chahiye", "Ok, noted"])
        self.assertEqual((meta["occurred_at"], [p["name"] for p in meta["participants"]]), ("2026-10-02T10:15", ["Dr Rao", "Akbar Ali"]))

    def test_plain(self):
        meta, lines = read_plain("Title line\n\nSecond line\n")
        self.assertEqual(([l["line_no"] for l in lines], meta["title"]), ([1, 2], "Title line"))


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.data = make_data()
        self.addCleanup(self.data.close)

    def test_contact_email_beats_title(self):
        self.assertEqual(route(self.data, [{"name": "", "email": "RAO@medbridge.example"}], "POS Rollout"), ("C04", "contact"))
        self.assertEqual(route(self.data, ["rhea.kulkarni@tailorbird.example"], "x"), ("C01", "contact"))

    def test_devx_only_plus_project_title(self):
        who = [{"name": "Akbar Ali", "email": "akbar@devx.example"}]
        self.assertEqual(route(self.data, who, "Weekly: Patient Booking App"), ("C04", "project_in_title"))

    def test_hint_wins_only_if_real(self):
        who = [{"name": "", "email": "rao@medbridge.example"}]
        self.assertEqual(route(self.data, who, "x", hint_area="C07"), ("C07", "hint"))
        self.assertEqual(route(self.data, who, "x", hint_area="C99"), ("C04", "contact"))

    def test_domain_calendar_title_and_client_name(self):
        self.assertEqual(route(self.data, [{"name": "New Person", "email": "sunita@carenest.example"}], "x"), ("C07", "domain"))
        self.assertEqual(route(self.data, [], "Quarterly review with the Orbit team"), ("C07", "calendar_event"))
        self.assertEqual(route(self.data, [], "Intro call with CareNest"), ("C07", "client_in_title"))
        self.assertEqual(route(self.data, [], "medbridge clinics: scope"), ("C04", "client_in_title"))
        self.assertEqual(route(self.data, [{"name": "", "email": "someone@gmail.com"}], "Lunch"), ("hold", "no_match"))
        self.assertEqual(route(self.data, [{"name": "", "email": "ceo@devx-demo.example"}], "DevX delivery review"), ("hold", "no_match"))

    def test_unknown_goes_to_hold(self):
        self.assertEqual(route(self.data, [{"name": "Zed", "email": "z@nowhere.example"}], "Lunch"), ("hold", "no_match"))
        self.assertEqual(route(self.data, [], ""), ("hold", "no_match"))


def meeting(title, *emails, speakers=()):
    return {"title": title, "calendar_invitees": [{"name": "n", "email": e} for e in emails],
            "transcript": [{"speaker": {"display_name": "s", "matched_calendar_invitee_email": e}, "text": "t", "timestamp": "00:00:01"}
                           for e in speakers]}


class TestShouldIngest(unittest.TestCase):
    def setUp(self):
        self.data = make_data()
        self.addCleanup(self.data.close)

    def test_cases(self):
        yes = [(meeting("Sync", "akbar@devx.example", "rao@medbridge.example"), "outside"),
               (meeting("Sync", "akbar@devx.example", speakers=["z@other.example"]), "outside"),
               (meeting("CareNest kickoff", "akbar@devx.example"), "names a client"),
               (meeting("Patient Booking App standup", "akbar@devx.example"), "names a client"),
               (meeting("Team chat #Brain", "akbar@devx.example"), "#brain")]
        for m, why in yes:
            ok, reason = should_ingest(m, self.data)
            self.assertTrue(ok, m["title"])
            self.assertIn(why, reason)
        for m in (meeting("Weekly planning", "akbar@devx.example", "dev@devx-demo.example"), meeting("Lunch"),
                  meeting("Weekly planning", "NEHA@DEVXLABS.AI")):
            self.assertEqual(should_ingest(m, self.data)[0], False, m["title"])
        self.assertEqual(should_ingest(json.dumps(meeting("Sync", "a@b.example")), self.data)[0], True)
        self.assertEqual(should_ingest(meeting("CareNest kickoff", "akbar@devx-demo.example"))[0], False)  # no data: title rule off

    def test_receive_skips_internal_meetings(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        mem = MemoryStore(os.path.join(tmp.name, "m.db"))
        self.addCleanup(mem.close)
        brain = BrainStore(mem)
        internal = json.dumps({**meeting("Weekly planning", "akbar@devx.example"), "recording_id": 1,
                               "transcript": [{"speaker": {"display_name": "Akbar"}, "text": "Plan the week", "timestamp": "00:00:02"}]})
        got = inbox.receive(brain, self.data, kind="fathom", content=internal)
        self.assertEqual((got["source_id"], got["routed_by"], got["lines"]), (None, "skipped", 0))
        self.assertIn("internal", got["skipped"])
        self.assertEqual(brain.sources(["hold"]), [])
        tagged = inbox.receive(brain, self.data, kind="fathom", content=internal.replace("Weekly planning", "Weekly planning #brain"))
        self.assertEqual((tagged["area_id"], tagged["routed_by"]), ("hold", "no_match"))
        forced = inbox.receive(brain, self.data, kind="fathom", content=internal, force=True, origin_ref="F2")
        self.assertTrue(forced["source_id"])


class TestLanguageAndLexicon(unittest.TestCase):
    def test_languages(self):
        self.assertEqual(detect_language("Reminders WhatsApp pe chahiye, SMS nahi"), "hinglish")
        self.assertEqual(detect_language("हमें रिमाइंडर चाहिए"), "hi")
        self.assertEqual(detect_language("We need reminders by Friday for the launch plan"), "en")
        self.assertEqual(detect_language("We need reminders, मुझे यह चाहिए और launch date भी batao"), "mixed")

    def test_lexicon_from_temp_file(self):
        lex = {"topics": {"reminders": {"en": ["reminder", "reminders"], "hinglish": ["yaad dilana"], "hi": ["रिमाइंडर"], "label": "R"},
                          "pricing": {"en": ["price"], "hinglish": [], "hi": [], "label": "P"}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lex.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(lex, f, ensure_ascii=False)
            loaded = load_lexicon(path)
        self.assertEqual(topics_in("Send Reminders and the price", loaded), ["reminders", "pricing"])
        self.assertEqual(topics_in("रिमाइंडर भेजो", loaded), ["reminders"])
        self.assertEqual(topics_in("priceless remindersX", loaded), [])
        self.assertEqual(topics_in("yaad dilana hai", loaded), ["reminders"])

    def test_missing_file_is_empty(self):
        self.assertEqual(load_lexicon("/no/such/file.json"), {"topics": {}})


class TestReceive(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mem = MemoryStore(os.path.join(tmp.name, "m.db"))
        self.addCleanup(self.mem.close)
        self.brain = BrainStore(self.mem)
        self.data = make_data()
        self.addCleanup(self.data.close)

    def test_fathom_routes_and_stores(self):
        got = inbox.receive(self.brain, self.data, kind="fathom", content=FATHOM, received_at="2026-10-03T08:00")
        self.assertEqual((got["area_id"], got["routed_by"], got["lines"], got["language"]), ("C04", "contact", 2, "hinglish"))
        src = self.brain.get_source(got["source_id"])
        self.assertEqual((src["origin_ref"], src["received_at"], src["raw_text"]), ("4711", "2026-10-03T08:00", FATHOM))

    def test_each_kind_lands_in_the_right_area(self):
        docx = inbox.receive(self.brain, self.data, kind="docx", content=make_docx(["Hi", "rao@medbridge.example"]), filename="a.docx")
        eml = inbox.receive(self.brain, self.data, kind="email", content=make_eml())
        chat = inbox.receive(self.brain, self.data, kind="chat", content=CHAT, hint_area="C04")
        plain = inbox.receive(self.brain, self.data, kind="plain", content="random note")
        self.assertEqual([r["area_id"] for r in (docx, eml, chat, plain)], ["C04", "C01", "C04", "hold"])
        self.assertEqual(chat["routed_by"], "hint")
        self.assertEqual(self.brain.get_source(plain["source_id"])["status"], "held")
        self.assertEqual(self.brain.get_source(eml["source_id"])["origin_ref"], "abc@tailorbird.example")

    def test_same_origin_ref_is_stored_once(self):
        a = inbox.receive(self.brain, self.data, kind="chat", content=CHAT, origin_ref="SRC9")
        b = inbox.receive(self.brain, self.data, kind="chat", content=CHAT, origin_ref="SRC9")
        self.assertEqual((a["source_id"], b["source_id"], b.get("duplicate")), (a["source_id"], a["source_id"], True))
        self.assertEqual(len(self.brain.sources(["hold", "C04", "C01"])), 1)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            inbox.receive(self.brain, self.data, kind="video", content="x")
        with self.assertRaises(ValueError):
            inbox.receive(self.brain, self.data, kind="plain", content="  \n ")


if __name__ == "__main__":
    unittest.main()
