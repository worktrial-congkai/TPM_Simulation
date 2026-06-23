-- Sim clock and scenario metadata
CREATE TABLE sim_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    owner_id TEXT,
    duration_minutes INTEGER,
    blocker_reason TEXT,
    critical_path INTEGER DEFAULT 0,
    depends_on TEXT
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    read_by_agent INTEGER DEFAULT 0
);

CREATE TABLE emails (
    id TEXT PRIMARY KEY,
    sender_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    read_by_agent INTEGER DEFAULT 0
);

CREATE TABLE calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    organizer_id TEXT,
    attendee_ids TEXT,
    event_type TEXT
);

CREATE TABLE meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    attendee_ids TEXT,
    meeting_type TEXT,
    transcript TEXT,
    completed INTEGER DEFAULT 0
);

CREATE TABLE docs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id TEXT,
    created_at TEXT NOT NULL,
    doc_type TEXT
);

CREATE TABLE milestones (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    depends_on_tasks TEXT
);

CREATE TABLE agent_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE coworker_state (
    coworker_id TEXT PRIMARY KEY,
    availability_until TEXT,
    current_commitments TEXT,
    last_interaction_at TEXT
);

CREATE TABLE coworker_policies (
    coworker_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    PRIMARY KEY (coworker_id, template_id)
);

CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    sim_time TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    result TEXT
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    seed INTEGER NOT NULL
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    source TEXT NOT NULL,
    actor_id TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    visibility TEXT NOT NULL DEFAULT 'public'
);

CREATE INDEX idx_events_pending_due
    ON events(start_ts, id)
    WHERE status = 'pending';

-- Test/debug marker table used by noop handler
CREATE TABLE handler_markers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    marker TEXT NOT NULL,
    created_at TEXT NOT NULL
);
