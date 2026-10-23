"""Adds dummy git activity (repos, scope items, pull requests, deploys) and the delivery_progress answer keys."""
import json
import random
import re
from collections import defaultdict
from datetime import date, timedelta

# The simple rules. first_detectable_on in the answer key is the first date each rule is true.
GIT_RULES = dict(
    unbilled_prs=3,          # merged PRs with no task, 30+ lines and not a chore, on one project ...
    chore_max_lines=30,      # ... PRs under 30 lines or titled "chore" are not counted
    rework_prs=4,            # PRs on one scope item that follow a client meeting
    behind_min_elapsed=0.30, # share of the project calendar used before the pace rule applies
    behind_ratio=0.6,        # behind when merged share of linked hours < 0.6 x elapsed share (checked on Mondays)
)
CASES = dict(unbilled_project="PR02", rework_project="PR04", behind_project="PR05",
             chore_project="PR01", two_revision_project="PR03", on_track_project="PR06")
OUTSIDE_SCOPE = [
    ("feat: loyalty points banner on cart", "loyalty-points-banner"),
    ("feat: gift wrapping option at checkout", "gift-wrapping-option"),
    ("feat: Instagram shop product feed", "instagram-shop-feed"),
    ("feat: festive countdown timer on home page", "festive-countdown-timer"),
    ("feat: referral code box", "referral-code-box"),
    ("feat: store pickup slot picker", "store-pickup-slots"),
]
CHORES = ["chore: bump deps", "chore: update lint config", "chore: fix typos in readme", "chore: bump deps"]
BRANCH_KIND = dict(Build="feat", Integrate="feat", Test="test", Polish="style", Review="refactor")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def feature_of(title):
    return re.sub(r" \(part \d+\)$", "", title.split(" ", 1)[1])


def mondays(start, end):
    d = start + timedelta(days=(7 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def behind_flags(start, end, today, merged_on, hours):
    """Mondays on which the pace rule is true. merged_on: task -> merge date; hours: linked task -> estimate."""
    total = sum(hours.values())
    out = {}
    for d in mondays(start, today):
        e = (d - start).days / max(1, (end - start).days)
        if e < GIT_RULES["behind_min_elapsed"]:
            continue
        m = sum(h for t, h in hours.items() if t in merged_on and merged_on[t] <= d) / total
        out[d] = (m < GIT_RULES["behind_ratio"] * e, m, e)
    return out


def first_stable_flag(flags):
    """First Monday from which the flag stays true to the end, or None."""
    first = None
    for d in sorted(flags):
        if flags[d][0]:
            first = first or d
        else:
            first = None
    return first


def add_git_activity(b, seed):
    rng = random.Random(seed + 7)
    rows, today = b.rows, b.today

    def stamp(d, lo, hi):
        return f"{d.isoformat()}T{rng.randint(lo, hi):02d}:{rng.choice(['00', '15', '30', '45'])}"

    projects = {r["project_id"]: r for r in rows["projects"]}
    sows = {r["sow_id"]: r for r in rows["sows"]}
    tasks_by = defaultdict(list)
    for t in rows["tasks"]:
        tasks_by[t["project_id"]].append(t)
    first_log = {}
    for lg in rows["time_logs"]:
        first_log[lg["task_id"]] = min(first_log.get(lg["task_id"], lg["date"]), lg["date"])
    as_of = {pid: b.proj[pid]["as_of"] for pid in projects}

    # ---- repos
    repos = {}
    for pid, p in projects.items():
        names = [slug(p["name"]) + "-web", slug(p["name"]) + "-api"] if len(tasks_by[pid]) >= 40 else [slug(p["name"])]
        repos[pid] = []
        for name in names:
            rid = b.nid("GR", 2)
            repos[pid].append(rid)
            b.add("repos", repo_id=rid, client_id=p["client_id"], project_id=pid, name=name)

    # ---- scope items from the signed SOW, and task links
    items = {}           # pid -> list of scope item rows
    for pid, p in projects.items():
        sow = sows[p["sow_id"]]
        titles = json.loads(sow["scope"])["in_scope"]
        w = [rng.uniform(0.5, 1.5) for _ in titles]
        est = [max(8, round(sow["estimate_hours"] * x / sum(w))) for x in w]
        start, end = date.fromisoformat(p["start_on"]), date.fromisoformat(p["planned_end_on"])
        items[pid] = []
        for i, title in enumerate(titles):
            due = start + timedelta(days=round((end - start).days * (0.25 + 0.75 * (i + 1) / len(titles))))
            items[pid].append(b.add("scope_items", scope_item_id=b.nid("SI", 3), sow_id=sow["sow_id"], project_id=pid,
                                    title=title, estimate_hours=est[i], due_on=due.isoformat()))
    scope_of = {}        # task_id -> scope item row
    for pid in projects:
        by_title = {it["title"]: it for it in items[pid]}
        for t in tasks_by[pid]:
            skip = rng.random() < 0.05
            if t["title"].startswith("Wait for") or skip or feature_of(t["title"]) not in by_title:
                continue
            scope_of[t["task_id"]] = by_title[feature_of(t["title"])]
            b.add("task_scope", task_id=t["task_id"], scope_item_id=scope_of[t["task_id"]]["scope_item_id"])

    # ---- pull requests (ids are given after sorting by open time)
    prs = []

    def new_pr(pid, repo, title, branch, author, op, mg, task, lines, revert=None, meeting=None):
        pr = dict(repo_id=repo, project_id=pid, title=title, branch=branch, author_id=author,
                  opened_at=stamp(op, 9, 12), merged_at=stamp(mg, 13, 19) if mg else None, task_id=task,
                  lines_changed=lines, revert_of_pr_id=None, after_meeting_id=meeting, _revert=revert,
                  _op=op, _mg=mg)
        prs.append(pr)
        return pr

    def repo_for(pid, task):
        r = repos[pid]
        it = scope_of.get(task["task_id"]) if task else None
        return r[items[pid].index(it) % len(r)] if it else rng.choice(r)

    for pid in projects:
        done = sorted((t for t in tasks_by[pid] if t["status"] == "done"), key=lambda t: (t["done_on"], t["task_id"]))
        stalled = {t["task_id"] for t in done[int(len(done) * 0.25):]} if pid == CASES["behind_project"] else set()
        for t in tasks_by[pid]:
            if t["status"] == "todo" or t["task_id"] not in first_log and t["status"] != "done":
                continue
            if t["status"] == "doing" and rng.random() < 0.4:
                continue
            tid, title = t["task_id"], t["title"]
            verb = title.split(" ", 1)[0]
            op = date.fromisoformat(first_log.get(tid, t["done_on"] or str(as_of[pid])))
            n_pr = 2 if t["estimate_hours"] >= 40 and rng.random() < 0.3 else 1
            for k in range(n_pr):
                mg = None
                if t["status"] == "done":
                    done_on = date.fromisoformat(t["done_on"])
                    lag = rng.randint(40, 110) if tid in stalled else rng.randint(0, 3)
                    mg = done_on + timedelta(days=lag)
                    if mg > as_of[pid]:
                        mg = None if tid in stalled else as_of[pid]
                lines = max(30, min(1200, int(t["estimate_hours"] * rng.uniform(6, 18))))
                suffix = " (follow-up)" if k else ""
                new_pr(pid, repo_for(pid, t), f"{tid} {title}{suffix}",
                       f"{BRANCH_KIND[verb]}/{tid}-{slug(title.split(' ', 1)[1])}{'-2' if k else ''}",
                       t["assignee_id"], min(op, mg) if mg else op, mg, tid, lines)

    def scope_tasks(pid, item, status="done"):
        return [t for t in tasks_by[pid] if scope_of.get(t["task_id"]) is item and t["status"] == status]

    def client_meetings(pid):
        ms = [m for m in rows["meetings"] if m["project_id"] == pid and m["kind"] in ("client_sync", "sprint_review")
              and date.fromisoformat(m["start_at"][:10]) + timedelta(days=5) <= as_of[pid]]
        return sorted(ms, key=lambda m: m["start_at"])

    def rework(pid, item, meetings):
        t = min(scope_tasks(pid, item), key=lambda t: (t["done_on"], t["task_id"]))
        for n, m in enumerate(meetings, 1):
            op = date.fromisoformat(m["start_at"][:10]) + timedelta(days=rng.randint(1, 2))
            mg = op + timedelta(days=rng.randint(1, 3))
            new_pr(pid, repo_for(pid, t), f"{t['task_id']} rework: {item['title']} after client feedback",
                   f"fix/{t['task_id']}-{slug(item['title'])}-feedback-{n}", t["assignee_id"], op, mg, t["task_id"],
                   rng.randint(20, 150), meeting=m["meeting_id"])

    def eligible_item(pid, skip=0):
        its = [it for it in items[pid] if len(scope_tasks(pid, it)) >= 1]
        return its[len(its) // 2 + skip]

    # DEL-2: one scope item reworked after five client meetings; look-alike: two revisions; one-offs elsewhere
    rw_pid = CASES["rework_project"]
    rw_item = eligible_item(rw_pid)
    rework(rw_pid, rw_item, client_meetings(rw_pid)[-5:] if len(client_meetings(rw_pid)) >= 5 else client_meetings(rw_pid))
    la_pid = CASES["two_revision_project"]
    la_item = eligible_item(la_pid, 1)
    rework(la_pid, la_item, client_meetings(la_pid)[-3:-1])
    for pid in (CASES["chore_project"], CASES["on_track_project"]):
        rework(pid, eligible_item(pid, -1), client_meetings(pid)[-2:-1])

    # DEL-1: merged work that links to no task and no scope item
    ub_pid = CASES["unbilled_project"]
    authors = sorted({t["assignee_id"] for t in tasks_by[ub_pid]})
    days = sorted(date(2026, 8, 17) + timedelta(days=rng.randint(0, 50)) for _ in OUTSIDE_SCOPE)
    for (title, br), mg in zip(OUTSIDE_SCOPE, days):
        mg = mg + timedelta(days=(7 - mg.weekday()) % 7 if mg.weekday() > 4 else 0)
        new_pr(ub_pid, rng.choice(repos[ub_pid]), title, f"feat/{br}", rng.choice(authors),
               mg - timedelta(days=rng.randint(1, 3)), mg, None, rng.randint(90, 420))
    # look-alike: small chores with no ticket; plus one-off unlinked work elsewhere (below the rule)
    ch_pid = CASES["chore_project"]
    ch_authors = sorted({t["assignee_id"] for t in tasks_by[ch_pid]})
    for i, title in enumerate(CHORES):
        mg = date(2026, 7, 20) + timedelta(days=21 * i + rng.randint(0, 6))
        new_pr(ch_pid, rng.choice(repos[ch_pid]), title, f"chore/{slug(title)}-{i + 1}", rng.choice(ch_authors),
               mg, mg, None, rng.randint(3, 25))
    for pid, title in (("PR03", "fix: hotfix for login redirect loop"), ("PR05", "chore: bump deps"),
                       ("PR06", "chore: update lint config")):
        a = sorted({t["assignee_id"] for t in tasks_by[pid]})
        mg = date(2026, 9, 14) + timedelta(days=rng.randint(0, 10))
        new_pr(pid, rng.choice(repos[pid]), title, f"{title.split(':')[0]}/{slug(title.split(': ')[1])}",
               rng.choice(a), mg, mg, None, 12 if title.startswith("chore") else 48)

    # reverts of a few merged PRs (they keep the original ticket)
    merged = [p for p in prs if p["_mg"] and p["task_id"] and p["after_meeting_id"] is None
              and p["_mg"] + timedelta(days=6) <= as_of[p["project_id"]]]
    for orig in rng.sample(merged, 3):
        mg = orig["_mg"] + timedelta(days=rng.randint(2, 5))
        new_pr(orig["project_id"], orig["repo_id"], f'Revert "{orig["title"]}"',
               "revert/" + orig["branch"].split("/", 1)[1], orig["author_id"], mg, mg, orig["task_id"],
               orig["lines_changed"], revert=orig)

    prs.sort(key=lambda p: (p["opened_at"], p["title"]))
    for p in prs:
        p["pr_id"] = b.nid("PL", 4)
    for p in prs:
        if p["_revert"]:
            p["revert_of_pr_id"] = p["_revert"]["pr_id"]
        b.add("pull_requests", **{k: v for k, v in p.items() if not k.startswith("_")})

    # ---- deploys: staging each Thursday, production every second staging (next day)
    by_repo = defaultdict(list)
    for p in prs:
        if p["_mg"]:
            by_repo[p["repo_id"]].append(p)
    repo_project = {r["repo_id"]: r["project_id"] for r in rows["repos"]}
    for rid, plist in sorted(by_repo.items()):
        pid = repo_project[rid]
        d = min(p["_mg"] for p in plist)
        d += timedelta(days=(3 - d.weekday()) % 7)
        staged, prodded, n_stage = set(), set(), 0
        while d <= as_of[pid]:
            new = [p for p in plist if p["_mg"] < d and p["pr_id"] not in staged]
            if new:
                staged.update(p["pr_id"] for p in new)
                n_stage += 1
                b.add("deploys", deploy_id=b.nid("DP", 4), repo_id=rid, project_id=pid, deployed_at=stamp(d, 15, 17),
                      env="staging", pr_ids=json.dumps([p["pr_id"] for p in new]))
                fri = d + timedelta(days=1)
                if n_stage % 2 == 0 and fri <= as_of[pid]:
                    go = sorted(staged - prodded)
                    prodded.update(go)
                    b.add("deploys", deploy_id=b.nid("DP", 4), repo_id=rid, project_id=pid, deployed_at=stamp(fri, 11, 14),
                          env="production", pr_ids=json.dumps(go))
            d += timedelta(days=7)

    b.keys["delivery_progress"] = build_keys(b, prs, items, scope_of, tasks_by, projects, as_of, rw_item, la_item)


def build_keys(b, prs, items, scope_of, tasks_by, projects, as_of, rw_item, la_item):
    today = b.today
    R = GIT_RULES

    def unbilled(p):
        return (p["_mg"] and p["task_id"] is None and p["lines_changed"] >= R["chore_max_lines"]
                and not p["title"].startswith("chore"))

    ub = defaultdict(list)
    for p in sorted(prs, key=lambda p: p["merged_at"] or ""):
        if unbilled(p):
            ub[p["project_id"]].append(p)
    assert {k for k, v in ub.items() if len(v) >= R["unbilled_prs"]} == {CASES["unbilled_project"]}, ub.keys()
    ub_pid = CASES["unbilled_project"]

    rev = defaultdict(list)
    for p in prs:
        if p["after_meeting_id"]:
            rev[scope_of[p["task_id"]]["scope_item_id"]].append(p)
    over = {k for k, v in rev.items() if len(v) >= R["rework_prs"]}
    assert over == {rw_item["scope_item_id"]}, over
    assert len(rev[la_item["scope_item_id"]]) == 2

    merged_on = defaultdict(dict)
    for p in prs:
        if p["_mg"] and p["task_id"] in scope_of:
            t = p["task_id"]
            merged_on[p["project_id"]][t] = min(p["_mg"], merged_on[p["project_id"]].get(t, p["_mg"]))
    stats = {}
    for pid, p in projects.items():
        if p["status"] != "active":
            continue
        hours = {t["task_id"]: t["estimate_hours"] for t in tasks_by[pid] if t["task_id"] in scope_of}
        flags = behind_flags(date.fromisoformat(p["start_on"]), date.fromisoformat(p["planned_end_on"]), today,
                             merged_on[pid], hours)
        stats[pid] = (first_stable_flag(flags), flags)
        if pid != CASES["behind_project"]:
            assert not any(f[0] for f in flags.values()), (pid, flags)
    bh_pid, ok_pid = CASES["behind_project"], CASES["on_track_project"]
    bh_first, bh_flags = stats[bh_pid]
    assert bh_first, bh_flags
    last = max(bh_flags)
    m_now, e_now = bh_flags[last][1], bh_flags[last][2]
    start = date.fromisoformat(projects[bh_pid]["start_on"])
    projected = start + timedelta(days=round((last - start).days / m_now))
    ok_last = stats[ok_pid][1][max(stats[ok_pid][1])]
    chores = [p for p in prs if p["project_id"] == CASES["chore_project"] and p["task_id"] is None]
    title = {it["scope_item_id"]: it["title"] for its in items.values() for it in its}

    cases = [
        dict(case_id="DEL-1", project_id=ub_pid, signal="merged_work_outside_scope",
             first_detectable_on=ub[ub_pid][R["unbilled_prs"] - 1]["merged_at"][:10], count=len(ub[ub_pid]),
             note="several merged PRs name no task and match no SOW scope item: real work outside the agreed scope"),
        dict(case_id="DEL-2", project_id=CASES["rework_project"], scope_item_id=rw_item["scope_item_id"],
             signal="scope_item_reworked_after_client_meetings",
             first_detectable_on=sorted(p["opened_at"] for p in rev[rw_item["scope_item_id"]])[R["rework_prs"] - 1][:10],
             count=len(rev[rw_item["scope_item_id"]]),
             note=f"'{title[rw_item['scope_item_id']]}' changed again after each client meeting"),
        dict(case_id="DEL-3", project_id=bh_pid, signal="merge_pace_too_slow_for_planned_end",
             first_detectable_on=bh_first.isoformat(), merged_share_today=round(m_now, 3),
             elapsed_share_today=round(e_now, 3), projected_finish=projected.isoformat(),
             note="scope work merges far slower than the calendar runs; planned end will be missed at this pace")]
    look = [
        dict(case_id="DEL-L1", project_id=CASES["chore_project"], signal="unlinked_small_chore_prs",
             first_detectable_on=None, count=len(chores),
             note="unlinked PRs are small chores (under 30 lines, titled chore): not unbilled work"),
        dict(case_id="DEL-L2", project_id=CASES["two_revision_project"], scope_item_id=la_item["scope_item_id"],
             signal="scope_item_two_revisions", first_detectable_on=None,
             count=len(rev[la_item["scope_item_id"]]), note="two client-feedback revisions only: normal"),
        dict(case_id="DEL-L3", project_id=ok_pid, signal="on_track", first_detectable_on=None,
             merged_share_today=round(ok_last[1], 3), elapsed_share_today=round(ok_last[2], 3),
             note="merge pace matches the calendar: on track")]
    return dict(cases=cases, look_alikes=look, rules=R)
