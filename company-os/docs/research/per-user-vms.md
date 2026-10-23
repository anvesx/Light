# One cloud VM per user: how agents browse and act

Written Oct 22, 2026. Research by a Claude (Sonnet) research agent that read vendor pages and docs, checked and written up by Claude (Opus). Prices are as stated on the vendor pages on that day. Each claim is marked **confirmed** (we read it on the source page) or **unverified** (a search result, a third-party page, or our own judgment).

## 1. The decision

Each user gets one virtual machine (VM) in the cloud. A VM is a full computer that runs on a cloud server. All of that user's agents work inside it, with a real browser, so they can use websites and apps that have no API.

Agents do not run on the user's Mac. On a Mac they use the user's CPU and memory, and they stop when the lid closes.

When a site needs a login, the agent sends the user a link. The user signs in once, inside the VM, through a live view. Then the agent carries on. The user never leaves the chat.

## 2. Who runs where

| Agent kind | Runs in | Why |
|---|---|---|
| Personal agents: travel, HR, meeting prep | The user's VM, one box each | They act for one person, with that person's logins |
| Finance | Its own VM | Money is high risk. It never shares a VM |
| Company agents, such as an infra monitor | A company service VM, with no browser | They act for the team and read APIs, not web pages |

## 3. Inside one user's VM

```
┌─────────────────┐  pulls jobs  ┌────────────────────────┐            ┌──────────────────┐
│ Control plane   │◄─────────────│ VM daemon              │            │ The user         │
│ job store,      │              │ runs inside the VM     │            │ signs in once    │
│ scheduler,      │              │ outbound HTTPS only,   │            │ through the      │
│ approvals, stop │              │ no inbound ports,      │            │ live view        │
│ switch, broker  │              │ sends checkpoints back │            └────────┬─────────┘
└─────────────────┘              └───┬─────────┬──────┬───┘                     ▼
                                     ▼         ▼      ▼                ┌──────────────────┐
              ┌───────────────┐ ┌───────────────┐ ┌───────────────┐    │ Live view        │
              │ Agent box:    │ │ Agent box: HR │ │ Agent box:    │◄───│ noVNC or WebRTC  │
              │ Travel        │ │ Linux user hr │ │ Meeting prep  │    │ read/write only  │
              │ Linux user,   │ │ own Chrome    │ │ own Chrome    │    │ during sign-in   │
              │ own Chrome    │ │ profile,      │ │ profile,      │    └──────────────────┘
              │ profile,      │ │ allowlist:    │ │ allowlist:    │
              │ allowlist     │ │ HR tool       │ │ Fathom, Slack │
              └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
                      ▼                 ▼                 ▼
              ┌─────────────────────────────────────────────────────┐
              │ Websites and apps: only the hosts on each agent's   │
              │ allowlist; every request logged                      │
              └─────────────────────────────────────────────────────┘
```

| Piece | How it works | Why |
|---|---|---|
| VM daemon | A small program inside the VM. It pulls jobs from the control plane over outbound HTTPS and sends checkpoints back | No inbound port is open, so nothing on the internet can call into the VM |
| Agent box | Each agent runs as its own Linux user, with its own Chrome profile and files | One agent cannot read another agent's cookies or files |
| Allowlist per agent | Firewall rules per Linux user. Deny by default | A tricked agent cannot send data to any site it likes |
| Live view | noVNC or WebRTC. Read/write only during a sign-in, read-only otherwise | The user signs in once. The agent never sees the password |
| Password broker | Fills a login from 1Password after the user approves that one fill | The secret never enters the model's context |
| Scrubber | Removes secrets from every snapshot, screenshot and log line | Grok Bot leaked a password through a browser snapshot (section 7) |
| Snapshot | Taken after each sign-in | Logins survive a pause or a crash |

**A shared VM is not a security wall by itself.** xAI tells Grok Bot users not to treat separate bots as a security boundary, because all of a user's bots share one computer (unverified: quoted on a blog, the xAI page was not opened). That is why each agent gets its own Linux user, profile and allowlist, and why finance gets its own VM. Separate Linux users are a weaker wall than separate VMs. That is the trade-off for cost (our judgment, unverified).

## 4. Sign-in: human takeover, then hand back

```
Agent            Control plane       User              Live view          Website
  │ login page found  │                  │                   │                  │
  │──────────────────►│ please sign in   │                   │                  │
  │ (agent pauses)    │─────────────────►│ opens the view    │                  │
  │                   │                  │──────────────────►│ types, with 2FA  │
  │                   │                  │                   │─────────────────►│
  │                   │◄─────────────────────── signed in ───│ (view read-only) │
  │◄──── resume ──────│ snapshot the VM  │                   │                  │
```

1. The agent meets a login page. It pauses and tells the control plane.
2. The control plane sends the user a link in Slack or the web page.
3. The user opens the live view and signs in, including any 2FA code.
4. The view switches to read-only. The control plane takes a snapshot of the VM.
5. The agent resumes, already signed in.

How hosts show the live view:
- E2B's desktop sandbox uses x11vnc and noVNC on port 6080, with an optional auth key. One viewer at a time (unverified, search result).
- Browserbase embeds the browser in an iframe, read-only or read/write (confirmed).
- Kernel uses a WebRTC viewer that can switch between read-only and interactive at run time (confirmed).
- xAI documents the same steps for Grok Bot: open the screen, log in, hand back (unverified, via a blog).

## 5. A VM's life

```
┌─────────┐   ┌─────────┐   ┌──────────────┐   ┌────────────────┐   ┌───────────────┐
│ Created │──►│ Running │──►│ Snapshot     │──►│ Paused         │──►│ Woken         │
│ first   │   │ billed  │   │ after each   │   │ idle 15 min;   │   │ a job is due; │
│ job     │   │ per sec │   │ sign-in      │   │ memory kept    │   │ resumes fast  │
└─────────┘   └────┬────┘   └──────────────┘   └────────────────┘   └───────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Stop switch: stop the VM, revoke its broker path, rotate any secret seen │
   └──────────────────────────────────────────────────────────────────────────┘
```

- Pause after 15 idle minutes (a starting value, not a measurement).
- Wake on a job from the scheduler: a schedule or an event.
- The stop switch also revokes the VM daemon's token at once.

## 6. Where to host the VMs

| Host | What it is | Pause and resume | Price (as stated, Oct 22, 2026) | Fit |
|---|---|---|---|---|
| E2B | Managed sandbox; desktop with noVNC | Pause keeps memory and disk. Resume about 1 s, pause about 4 s per GiB of RAM (confirmed) | $0.000014 per vCPU-second and $0.0000045 per GiB-second; 2 vCPU and 4 GiB is about $0.17 an hour; Pro plan $150 a month; one run lasts at most 24 hours on Pro (confirmed) | Good start. India region not checked |
| Daytona | Managed sandbox; VNC and computer use | VMs can pause and resume (confirmed) | $0.0504 per vCPU-hour, $0.0162 per GiB-hour (confirmed) | Good start. US and EU regions only (confirmed) |
| Modal Sandboxes | Managed sandbox | Not checked | $0.00003942 per core-second (a core is 2 vCPU), $0.00000667 per GiB-second; choosing a region costs 1.15 to 1.75 times more (confirmed) | Possible |
| Cloudflare Containers | Containers | Sleep when idle; billing stops (confirmed) | $0.000020 per vCPU-second, $0.0000025 per GiB-second, plus the $5 a month Workers Paid plan (confirmed) | Desktop support not checked |
| Fly.io Machines | Small VMs | A stopped machine pays only for disk (confirmed) | shared-cpu-2x with 2 GB is $13.39 a month (confirmed) | Mumbai region not confirmed |
| AWS EC2, Mumbai (`ap-south-1`) | A full VM | Stop and start; disk snapshots | t4g.medium (2 vCPU, 4 GiB) about $0.0224 an hour (unverified: third-party price lists) | Cheapest always on; data stays in India |
| Browserbase, Kernel, Steel, Hyperbrowser | Managed browsers only | Kernel goes to standby after 5 s idle and stops billing (confirmed) | Browserbase $20 a month with 100 hours, then $0.12 an hour; Kernel headful $0.48 an hour (confirmed) | Browser only. They cannot run other apps |

**Our suggestion:** start on E2B or Daytona, behind a small VM provider interface (create, pause, resume, snapshot, stop). If the data must stay in India, or cost matters at scale, move to EC2 in Mumbai. The interface keeps that move small.

## 7. Credentials

- **1Password Secure Agentic Autofill** fills a login after a human approves it, and the model never sees the password. It launched in early access in Oct 2025 with Browserbase (unverified, search result). Whether it works outside Browserbase is not checked.
- **1Password service accounts** give a program access to chosen vaults (confirmed). Use them for API keys, not for browser logins.
- **Bitwarden** has an agent access SDK in alpha since Mar 2026 (unverified, search result).
- **Grok Bot** uses 1Password with an approval for each fill (unverified, via a blog).
- **A known leak:** on Oct 5, 2026 a Grok Bot user reported a password shown in plain text in a browser snapshot and the transcript. Staff said a fix was in progress (confirmed, Cursor forum). Lesson: scrub every snapshot and log line, and test it with a planted secret.

## 8. What it costs

Estimates from the prices above, with 730 hours in a month.

| Setup | Per user per month | 10 users | 100 users | 1,000 users |
|---|---|---|---|---|
| EC2 Mumbai, always on | About $19 ($16.35 compute + about $3 disk) | $190 | $1,900 | $19,000 |
| E2B, paused when idle, 2 busy hours a day | About $10, plus $150 a month for the plan | $250 | $1,150 | $10,100 |
| E2B, always on | About $121 | $1,210 | $12,100 | $121,000 |

Always on is cheapest on EC2. Pausing pays off only on per-second hosts like E2B. Pause-time storage prices and plan concurrency limits are not checked.

## 9. New folders (planned)

| Folder | Files | Job |
|---|---|---|
| `control_plane/vms/` | `vm_provider.py` (one interface; E2B, Daytona or EC2 adapters), `vm_lifecycle.py`, `live_view.py` | Create, pause, wake and stop user VMs |
| `vm_daemon/` (runs inside each VM) | `daemon.py`, `agent_box.py` (Linux user, Chrome profile, firewall rules) | Pull jobs, run agent boxes |

## 10. Open questions

| Question | Our suggestion |
|---|---|
| Which host runs the user VMs? | E2B or Daytona to start |
| Must client data stay in India? | If yes, EC2 in Mumbai |
| How long before an idle VM pauses? | 15 minutes, then measure |
| Does 1Password's agent autofill work outside Browserbase? | Test it before we depend on it |

## Sources

Opened and read:
- https://e2b.dev/pricing
- https://docs.e2b.dev/sandbox/persistence
- https://www.daytona.io/pricing
- https://www.daytona.io/docs/en/sandbox-management/
- https://www.browserbase.com/pricing
- https://docs.browserbase.com/features/session-live-view
- https://docs.fly.io/about/pricing
- https://www.kernel.sh/docs/info/pricing
- https://www.kernel.sh/docs/browsers/live-view
- https://modal.com/pricing
- https://developers.cloudflare.com/containers/pricing/
- https://www.1password.dev/service-accounts/
- https://forum.cursor.com/t/grok-bot-browser-snapshot-shows-a-password-filled-by-the-secure-form-requestuserform-in-plain-text/173748
- https://newfacedesign.com/blog/grok-bot-1password-agent-logins
- https://aws.amazon.com/ec2/pricing/on-demand/ (no Mumbai prices shown)

Search results only, not opened: 1Password and Browserbase press release (Oct 2025), github.com/e2b-dev/desktop, Bitwarden's AI agent identity page, instances.vantage.sh (t4g.medium).
