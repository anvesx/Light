"""Text the generator draws from: meeting topics, filler lines, Slack lines and expense notes."""

# Each topic: question, decisions (second one can replace the first), fact, opinion, task as (side, text).
TOPICS = {
    "payment-gateway": dict(
        q="Which payment gateway should we use for card and UPI payments in {product}?",
        d=["We will use the bank-backed gateway for {product} with UPI collect switched on.",
           "We will move {product} to the aggregator gateway because settlement is faster."],
        f="The current gateway charges two percent on every card payment.",
        o="I think the aggregator gateway has better documentation for our stack.",
        t=("client", "Share the payment gateway sandbox keys with the DevX team.")),
    "launch-date": dict(
        q="What launch date should we commit to for {product}?",
        d=["We will launch {product} on the first Monday of the festive month.",
           "We will move the launch of {product} by two weeks to fit extra testing."],
        f="Last year the festive rush started in the second week of the month.",
        o="I think a launch in the festive week is risky for support.",
        t=("devx", "Draft the launch checklist for {product}.")),
    "single-sign-on": dict(
        q="Should staff sign in with the company email single sign-on?",
        d=["Staff will sign in with company email single sign-on from day one.",
           "We will start with password login and add single sign-on in phase two."],
        f="The client uses one email provider for all staff.",
        o="I feel password login is faster to ship first.",
        t=("devx", "Ask the client IT team for the single sign-on settings.")),
    "data-migration": dict(
        q="Who will clean the old records before we migrate them into {product}?",
        d=["The client team will clean the old records and DevX will run the migration.",
           "DevX will migrate the old records as they are and mark bad rows for later cleanup."],
        f="About 40,000 rows sit in an old spreadsheet export.",
        o="I think migrating dirty data will cost us more support time later.",
        t=("client", "Send the old data export to DevX in the shared folder.")),
    "report-format": dict(
        q="Which format do managers want for the weekly report, PDF or spreadsheet?",
        d=["The weekly report will be a spreadsheet export with a PDF summary page.",
           "The weekly report will be PDF only, sent every Monday morning."],
        f="Managers today copy numbers by hand into a slide.",
        o="I think a spreadsheet is more useful for the finance team.",
        t=("client", "Share a sample of the current weekly report.")),
    "user-roles": dict(
        q="Which user roles do we need, and who can approve what?",
        d=["We will start with three roles: admin, manager and staff.",
           "We will add a fourth role, auditor, with read-only access."],
        f="Today every user shares one admin password.",
        o="I think fewer roles will be easier to train.",
        t=("client", "List the people for each user role.")),
    "notification-channel": dict(
        q="Should customer alerts go by SMS or by WhatsApp?",
        d=["Customer alerts will go by WhatsApp first, with SMS as the fallback.",
           "Customer alerts will go by SMS only until the WhatsApp approval comes through."],
        f="The WhatsApp business approval takes about two weeks.",
        o="I think customers answer faster on WhatsApp.",
        t=("devx", "Start the WhatsApp business account approval.")),
    "hosting-region": dict(
        q="Which cloud region should host the data for {product}?",
        d=["We will host {product} in the Mumbai region to keep data in India.",
           "We will add a second region for backups only."],
        f="The client contract says customer data must stay in India.",
        o="I feel one region is enough for the first year.",
        t=("devx", "Confirm the data residency rule with the client legal team.")),
    "offline-mode": dict(
        q="Does {product} need to work when the internet is down?",
        d=["{product} will keep working offline for up to four hours and sync later.",
           "Offline mode will be cut from phase one to save eight weeks."],
        f="Some sites lose internet for an hour or two every week.",
        o="I think offline sync is the riskiest part of the plan.",
        t=("devx", "List the screens that must work offline.")),
    "branding-guidelines": dict(
        q="Do we have the final brand colours and fonts for {product}?",
        d=["We will use the new brand colours and the rounded font for {product}.",
           "We will keep the old logo until the new one is approved."],
        f="The new brand guide was approved last month by the client board.",
        o="I think the new colours need a contrast check.",
        t=("client", "Send the brand guide and logo files.")),
    "api-rate-limits": dict(
        q="What rate limit will the partner API allow for {product}?",
        d=["We will cap calls at 60 per minute and cache replies for five minutes.",
           "We will ask the partner to raise the limit before launch."],
        f="The partner API blocks callers after 100 calls a minute.",
        o="I think caching is a safer fix than asking for a higher limit.",
        t=("devx", "Ask the partner to confirm the real rate limit in writing.")),
    "test-devices": dict(
        q="Which phones and tablets must we test on?",
        d=["We will test on the five most used Android phones and two iPads.",
           "We will add the older tablets the team still uses."],
        f="The client's own analytics show Android is 80 percent of users.",
        o="I think testing on old tablets will find real problems.",
        t=("client", "Share the device list from the client's analytics.")),
    "holiday-freeze": dict(
        q="When should we freeze releases for the festive season?",
        d=["We will freeze releases from the first of the festive month until it ends.",
           "We will allow urgent fixes during the freeze with the client's approval."],
        f="Last festive season a late release caused two hours of downtime.",
        o="I think a short freeze is better than none.",
        t=("devx", "Put the freeze dates in the shared calendar.")),
    "training-plan": dict(
        q="How will the client's staff be trained before go-live?",
        d=["DevX will run two live training sessions and share short videos.",
           "The client will name one champion per site who trains the others."],
        f="Staff turnover is high, so new people join every month.",
        o="I think short videos work better than long sessions.",
        t=("devx", "Record a ten minute walkthrough video.")),
    "hardware-support": dict(
        q="Which handheld scanners and printers must {product} support?",
        d=["We will support the two scanner models the client already owns.",
           "We will add support for the new label printer in phase two."],
        f="The client owns about 30 scanners of two models.",
        o="I think we should not buy new hardware yet.",
        t=("client", "Send the model names of the scanners and printers.")),
    "invoice-numbering": dict(
        q="What invoice numbering format does the finance team need?",
        d=["Invoices will use the format year, site code, then a running number.",
           "The running number will reset on the first of April each year."],
        f="The tax rules need unbroken invoice numbers for each financial year.",
        o="I think the site code makes audits easier.",
        t=("devx", "Confirm the tax invoice format with the client accountant.")),
    "language-support": dict(
        q="Which languages should {product} support at launch?",
        d=["{product} will launch in English and Hindi.",
           "We will add Marathi after launch based on usage."],
        f="About a third of users prefer Hindi.",
        o="I think translations should be reviewed by a native speaker.",
        t=("client", "Collect the Hindi text from the client team.")),
    "backup-policy": dict(
        q="How long should we keep backups of the data?",
        d=["We will keep daily backups for 30 days and monthly backups for a year.",
           "We will test a restore every quarter."],
        f="The client's audit team asks for a restore test each year.",
        o="I feel monthly backups for a year is more than enough.",
        t=("devx", "Write the backup and restore note for the client.")),
    "pilot-group": dict(
        q="Which group should try {product} first?",
        d=["The pilot will run with one site and ten users for two weeks.",
           "We will widen the pilot to three sites after the first review."],
        f="The client has one site with a very supportive manager.",
        o="I think a small pilot will find most of the problems.",
        t=("client", "Name the pilot site and the ten users.")),
    "support-hours": dict(
        q="What support hours does the client expect after launch?",
        d=["Support will run from nine to seven on weekdays for the first month.",
           "We will add Saturday support during the festive weeks."],
        f="The client's busiest hours are in the evening.",
        o="I think evening support matters more than early morning.",
        t=("devx", "Share the support contact list with the client.")),
    "analytics-events": dict(
        q="Which user actions should we track for reports?",
        d=["We will track the twelve key actions listed in the shared sheet.",
           "We will not store customer phone numbers in analytics."],
        f="The client's marketing team wants weekly funnel numbers.",
        o="I think fewer events with clean names are better.",
        t=("devx", "Review the event list with the marketing team.")),
    "vendor-sandbox": dict(
        q="When will the partner give us a test environment?",
        d=["The partner will open a test environment by the end of next week.",
           "We will use mock data until the partner test environment is ready."],
        f="The partner's team is small and answers emails in two days.",
        o="I think we should not wait on the partner.",
        t=("devx", "Chase the partner for the test environment.")),
}

FILLER_FACTS = [
    ("sprint-progress", "Sprint {n} closed {a} of {b} planned tasks for {product}."),
    ("staging-site", "The staging site for {product} was refreshed with the latest build."),
    ("bug-status", "No blocking bugs are open on {product} this week."),
    ("bug-status", "Two small bugs found in testing were fixed the same day."),
]
FILLER_TASKS = [
    ("next-demo", "devx", "Prepare the demo build for the next review of {product}."),
    ("shared-plan", "devx", "Update the shared plan for {product} with the new dates."),
    ("meeting-notes", "devx", "Send the meeting notes to everyone who joined."),
    ("test-feedback", "client", "Test the latest build of {product} and send comments."),
]
FILLER_OPINIONS = [
    ("team-pace", "I think the team is on a good pace this sprint."),
    ("review-format", "I feel the demo was clear and useful."),
    ("review-format", "I think we should keep the sprint reviews short."),
]

GROWTH_QUESTION = ("budget-range", "What budget range does the team have in mind for this work?")
GROWTH_TASK = ("proposal", "Send a short proposal and a rough plan after this call.")
GROWTH_OPINION = ("timeline", "I think the timeline the client has in mind is tight but possible.")

INTERNAL_ITEMS = [  # kind, topic, text
    ("decision", "hiring-plan", "We will hire two engineers in the next quarter."),
    ("decision", "code-review-rules", "Every change needs one reviewer before it merges."),
    ("decision", "on-call-rota", "The on-call rota will rotate weekly among engineers."),
    ("decision", "travel-policy", "Client visits need approval from the project lead and finance."),
    ("decision", "tooling-budget", "We will keep the tooling budget flat this quarter."),
    ("question", "estimating-method", "How should we add buffer to estimates for new clients?"),
    ("question", "client-health", "Which clients need extra attention this month?"),
    ("question", "hiring-plan", "Do we need a second designer?"),
    ("task", "release-process", "Write the release checklist and share it with all leads."),
    ("task", "tooling-budget", "Review the software subscriptions and list unused ones."),
    ("fact", "client-health", "Two clients have asked for a faster response time."),
    ("fact", "on-call-rota", "Last month had three late-night alerts."),
    ("fact", "travel-policy", "Travel spend was higher than planned last month."),
    ("opinion", "estimating-method", "I think we should add a 15 percent buffer to every estimate."),
    ("opinion", "code-review-rules", "I think pairing on tricky changes saves review time."),
]

SOW_CHANGE_TEXTS = [  # text with {feature}, hours, accepted
    ("Add {feature} to phase one", 24, 1),
    ("Remove {feature} from phase one", -16, 1),
    ("Add a Hindi version of {feature}", 20, 1),
    ("Add an extra approval step to {feature}", 12, 0),
    ("Move {feature} to phase two", -20, 1),
]

DEVX_SLACK = [
    "Staging build for {product} is updated. Please test {feature} and share comments.",
    "This week we closed {n} tasks on {product}.",
    "Reminder: the next review for {product} is coming up. Please send your questions before then.",
    "We found a small issue in {feature} and fixed it. No action needed from your side.",
    "Can you confirm the data we need for {feature}? We are waiting on it.",
    "The {feature} screen is ready for your review.",
    "Quick update: {feature} passed our internal tests.",
]
CLIENT_SLACK = [
    "Thanks, the {feature} screen looks good to us.",
    "Can we get a short call about {feature}? Our team has a few comments.",
    "We tried the staging build. One comment on {feature}: the labels need to be bigger.",
    "Our team will send the data for {feature} by Friday.",
    "Please share the plan for next week.",
    "We approved the changes for {feature}. Please go ahead.",
    "Who is the right person to ask about the {feature} rollout?",
]
NUDGES = [
    "Hi {name}, a gentle reminder that we still need your input to continue on {product}.",
    "Hi {name}, checking in on the open points from the last review. Can you share an update?",
    "Hi {name}, the team is blocked on {product} until we hear from you.",
    "Hi {name}, can we book a short call this week to unblock {product}?",
]
INTERNAL_GENERAL = [
    "Standup notes are in the shared folder.",
    "Reminder: update your time logs before Friday evening.",
    "Lunch order for the Friday team meet closes at noon.",
    "Please review the new coding checklist in the wiki.",
    "The office wifi will be down for 30 minutes tonight.",
    "Please share your wins for the monthly update.",
]
INTERNAL_FINANCE = [
    "Reminder: send all vendor invoices to finance by the 25th.",
    "The cloud bill for this month is in. I will check it against last month.",
    "Please attach a project code to every expense claim.",
    "Payments for approved invoices go out on Thursdays.",
]
INTERNAL_GROWTH = [
    "New lead from a referral. I will log it today.",
    "The proposal is with the client. I will follow up on Friday.",
    "Call notes are in the growth folder.",
    "Two new leads came from the website form this week.",
]

EXPENSE_NOTES = {
    "travel": ["Client visit travel", "Site visit cab fare", "Train ticket for a client workshop"],
    "food": ["Team lunch", "Snacks for a client meeting", "Dinner during a release night"],
    "software": ["Tool licence", "Plugin subscription", "Annual domain renewal"],
    "hardware": ["Keyboard and mouse", "Monitor cable and adapter", "Webcam for meetings"],
    "other": ["Courier charges", "Printing and stationery", "Co-work day pass"],
}
GROWTH_CALL_SUMMARY = "Intro call with {contact}. {fact} They asked about timeline and budget."
REFUND_REASONS = ["size issue", "fabric defect", "changed mind", "gift return", "wrong item"]
