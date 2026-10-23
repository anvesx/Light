-- Dummy company systems. JSON columns hold JSON text. Money is INR. Dates are ISO text.
CREATE TABLE clients (
    client_id TEXT PRIMARY KEY, name TEXT NOT NULL, industry TEXT,
    csm_id TEXT REFERENCES people(person_id), account_manager_id TEXT REFERENCES people(person_id),
    status TEXT NOT NULL CHECK (status IN ('active','paused','churned','prospect','lost')));
CREATE TABLE people (
    person_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, role TEXT NOT NULL, team TEXT,
    is_devx INTEGER NOT NULL, client_id TEXT REFERENCES clients(client_id),
    monthly_salary_inr INTEGER, manager_id TEXT REFERENCES people(person_id));
CREATE TABLE leads (
    lead_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id), source TEXT,
    owner_id TEXT REFERENCES people(person_id),
    stage TEXT NOT NULL CHECK (stage IN ('new','qualified','proposal','negotiation','won','lost')),
    created_on TEXT, won_on TEXT, value_inr INTEGER, lost_reason TEXT);
CREATE TABLE growth_calls (
    call_id TEXT PRIMARY KEY, lead_id TEXT REFERENCES leads(lead_id),
    client_id TEXT REFERENCES clients(client_id), date TEXT,
    owner_id TEXT REFERENCES people(person_id), attendees TEXT, summary TEXT);
CREATE TABLE sows (
    sow_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id),
    project_id TEXT REFERENCES projects(project_id), version INTEGER,
    status TEXT NOT NULL CHECK (status IN ('draft','sent','signed','superseded')),
    created_on TEXT, signed_on TEXT, estimate_hours INTEGER, price_inr INTEGER, scope TEXT);
CREATE TABLE sow_changes (
    change_id TEXT PRIMARY KEY, sow_id TEXT REFERENCES sows(sow_id), date TEXT,
    requested_by TEXT REFERENCES people(person_id), change_text TEXT, hours_delta INTEGER,
    accepted INTEGER NOT NULL);
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id), name TEXT NOT NULL,
    lead_id TEXT REFERENCES people(person_id), csm_id TEXT REFERENCES people(person_id),
    start_on TEXT, planned_end_on TEXT,
    status TEXT NOT NULL CHECK (status IN ('active','done','paused')),
    sow_id TEXT REFERENCES sows(sow_id));
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id), title TEXT NOT NULL,
    assignee_id TEXT REFERENCES people(person_id), estimate_hours REAL,
    status TEXT NOT NULL CHECK (status IN ('todo','doing','done')), due_on TEXT, done_on TEXT);
CREATE TABLE time_logs (
    log_id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(task_id),
    person_id TEXT REFERENCES people(person_id), date TEXT, hours REAL);
CREATE TABLE meetings (
    meeting_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id),
    project_id TEXT REFERENCES projects(project_id),
    kind TEXT NOT NULL CHECK (kind IN ('growth_call','discovery','sow_review','sprint_review','client_sync','internal')),
    start_at TEXT, attendees TEXT, title TEXT, transcript TEXT);
CREATE TABLE meeting_items (
    item_id TEXT PRIMARY KEY, meeting_id TEXT REFERENCES meetings(meeting_id),
    kind TEXT NOT NULL CHECK (kind IN ('decision','task','question','fact','opinion')),
    text TEXT NOT NULL, topic TEXT, owner_id TEXT REFERENCES people(person_id), status TEXT,
    supersedes_item_id TEXT REFERENCES meeting_items(item_id),
    answers_item_id TEXT REFERENCES meeting_items(item_id));
CREATE TABLE calendar_events (
    event_id TEXT PRIMARY KEY, title TEXT, start_at TEXT, attendees TEXT,
    client_id TEXT REFERENCES clients(client_id), project_id TEXT REFERENCES projects(project_id),
    meeting_id TEXT REFERENCES meetings(meeting_id));
CREATE TABLE slack_messages (
    msg_id TEXT PRIMARY KEY, channel TEXT NOT NULL, client_id TEXT REFERENCES clients(client_id),
    author_id TEXT REFERENCES people(person_id), ts TEXT, text TEXT);
CREATE TABLE vendors (
    vendor_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, created_on TEXT);
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY, vendor_id TEXT REFERENCES vendors(vendor_id), invoice_no TEXT,
    amount_inr INTEGER, date TEXT, project_id TEXT REFERENCES projects(project_id),
    status TEXT NOT NULL CHECK (status IN ('unpaid','paid')));
CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY, invoice_id TEXT REFERENCES invoices(invoice_id),
    vendor_id TEXT REFERENCES vendors(vendor_id), amount_inr INTEGER, date TEXT,
    approved_by TEXT REFERENCES people(person_id));
CREATE TABLE expenses (
    expense_id TEXT PRIMARY KEY, person_id TEXT REFERENCES people(person_id), team TEXT,
    category TEXT NOT NULL CHECK (category IN ('travel','food','software','hardware','other')),
    amount_inr INTEGER, date TEXT, project_id TEXT REFERENCES projects(project_id), note TEXT);
CREATE TABLE budgets (
    budget_id TEXT PRIMARY KEY, team TEXT, month TEXT, category TEXT, amount_inr INTEGER);
CREATE TABLE stores (
    store_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id), name TEXT NOT NULL,
    city TEXT, manager_id TEXT REFERENCES people(person_id));
CREATE TABLE pos_orders (
    order_id TEXT PRIMARY KEY, store_id TEXT REFERENCES stores(store_id),
    staff_id TEXT REFERENCES people(person_id), date TEXT, amount_inr INTEGER,
    customer_ref TEXT, payment_method TEXT);
CREATE TABLE pos_refunds (
    refund_id TEXT PRIMARY KEY, order_id TEXT REFERENCES pos_orders(order_id),
    store_id TEXT REFERENCES stores(store_id), staff_id TEXT REFERENCES people(person_id),
    approver_id TEXT REFERENCES people(person_id), date TEXT, amount_inr INTEGER,
    method TEXT NOT NULL CHECK (method IN ('cash','upi','card','gift_voucher')), reason TEXT);
CREATE TABLE pos_discounts (
    discount_id TEXT PRIMARY KEY, order_id TEXT REFERENCES pos_orders(order_id),
    store_id TEXT REFERENCES stores(store_id), requester_id TEXT REFERENCES people(person_id),
    approver_id TEXT REFERENCES people(person_id), pct INTEGER, otp_retries INTEGER, date TEXT);
CREATE TABLE alterations (
    alt_id TEXT PRIMARY KEY, order_id TEXT REFERENCES pos_orders(order_id),
    store_id TEXT REFERENCES stores(store_id), staff_id TEXT REFERENCES people(person_id),
    kind TEXT NOT NULL CHECK (kind IN ('alteration','remake')), date TEXT, charged INTEGER NOT NULL);
-- Git activity (T13): repos, SOW scope items, pull requests and deploys. Built after all tables above.
CREATE TABLE repos (
    repo_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id),
    project_id TEXT REFERENCES projects(project_id), name TEXT NOT NULL);
CREATE TABLE scope_items (
    scope_item_id TEXT PRIMARY KEY, sow_id TEXT REFERENCES sows(sow_id),
    project_id TEXT REFERENCES projects(project_id), title TEXT NOT NULL, estimate_hours INTEGER, due_on TEXT);
CREATE TABLE task_scope (
    task_id TEXT REFERENCES tasks(task_id), scope_item_id TEXT REFERENCES scope_items(scope_item_id));
CREATE TABLE pull_requests (
    pr_id TEXT PRIMARY KEY, repo_id TEXT REFERENCES repos(repo_id),
    project_id TEXT REFERENCES projects(project_id), title TEXT NOT NULL, branch TEXT,
    author_id TEXT REFERENCES people(person_id), opened_at TEXT, merged_at TEXT,
    task_id TEXT REFERENCES tasks(task_id), lines_changed INTEGER,
    revert_of_pr_id TEXT REFERENCES pull_requests(pr_id),
    after_meeting_id TEXT REFERENCES meetings(meeting_id));
CREATE TABLE deploys (
    deploy_id TEXT PRIMARY KEY, repo_id TEXT REFERENCES repos(repo_id),
    project_id TEXT REFERENCES projects(project_id), deployed_at TEXT,
    env TEXT NOT NULL CHECK (env IN ('staging','production')), pr_ids TEXT);
-- Client requests (T16): what developers need from clients, and how each request went. Built after all tables above.
CREATE TABLE project_profiles (
    project_id TEXT PRIMARY KEY REFERENCES projects(project_id),
    platform TEXT NOT NULL CHECK (platform IN ('shopify','web','mobile')),
    uses_client_domain INTEGER NOT NULL, uses_client_cloud INTEGER NOT NULL);
CREATE TABLE client_requests (
    request_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id),
    project_id TEXT REFERENCES projects(project_id), task_id TEXT REFERENCES tasks(task_id),
    requested_by TEXT REFERENCES people(person_id),
    kind TEXT NOT NULL CHECK (kind IN ('shopify_collaborator_access','theme_access','app_install_approval','dns_record',
                                       'cloud_role','api_keys_via_vault','content_assets','decision')),
    title TEXT NOT NULL, details TEXT, created_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('open','asked','reminded','granted','verified','failed_verification','cancelled')),
    owner_contact_id TEXT REFERENCES people(person_id), granted_at TEXT, verified_at TEXT);
CREATE TABLE client_request_events (
    event_id TEXT PRIMARY KEY, request_id TEXT REFERENCES client_requests(request_id), at TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('requested','asked','reminder','client_reply','granted','verification_passed',
                                       'verification_failed','escalated')),
    by_id TEXT REFERENCES people(person_id),
    channel TEXT NOT NULL CHECK (channel IN ('slack','email','meeting')), text TEXT);
CREATE TABLE access_checks (
    check_id TEXT PRIMARY KEY, request_id TEXT REFERENCES client_requests(request_id), at TEXT, target TEXT,
    result TEXT NOT NULL CHECK (result IN ('pass','fail')), detail TEXT);
CREATE TABLE task_blocks (
    task_id TEXT REFERENCES tasks(task_id), request_id TEXT REFERENCES client_requests(request_id),
    blocked_from TEXT, blocked_to TEXT);
-- Trips (spend advisor): business trips, hotel stays and what was available. Built after all tables above.
CREATE TABLE trips (
    trip_id TEXT PRIMARY KEY, person_id TEXT REFERENCES people(person_id), team TEXT,
    purpose TEXT NOT NULL CHECK (purpose IN ('client meeting','internal','event')),
    client_id TEXT REFERENCES clients(client_id), from_city TEXT, to_city TEXT,
    depart_on TEXT, return_on TEXT, booked_on TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('flight','train')), carrier TEXT,
    cabin TEXT NOT NULL CHECK (cabin IN ('economy','premium','business')),
    fare_inr INTEGER, expense_id TEXT REFERENCES expenses(expense_id), duration_hours REAL, note TEXT,
    depart_time TEXT, flight_no TEXT);
CREATE TABLE hotel_stays (
    stay_id TEXT PRIMARY KEY, trip_id TEXT REFERENCES trips(trip_id), city TEXT, hotel TEXT,
    nights INTEGER, rate_inr INTEGER, total_inr INTEGER);
CREATE TABLE fare_options (
    option_id TEXT PRIMARY KEY, trip_id TEXT REFERENCES trips(trip_id), seen_on TEXT, carrier TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('flight','train')),
    cabin TEXT NOT NULL CHECK (cabin IN ('economy','premium','business')), depart_time TEXT, fare_inr INTEGER,
    flight_no TEXT, arrive_time TEXT);
CREATE TABLE hotel_options (
    option_id TEXT PRIMARY KEY, stay_id TEXT REFERENCES hotel_stays(stay_id), hotel TEXT, rate_inr INTEGER);
CREATE TABLE city_hotel_rates (city TEXT PRIMARY KEY, policy_rate_inr INTEGER);
-- What each won client was billed per month (brain revenue). Built last, with the brain records.
CREATE TABLE client_invoices (
    invoice_id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(client_id),
    project_id TEXT REFERENCES projects(project_id), month TEXT, amount_inr INTEGER,
    status TEXT NOT NULL CHECK (status IN ('paid','sent','overdue')));
