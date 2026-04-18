# I Built a Self-Healing AI Agent System

Six months ago, I was babysitting infrastructure. Today it mostly babysits itself. I want to write honestly about what that took, because most posts on this topic skip the embarrassing parts.

Here's the embarrassing part: for a long time, I *was* the uptime strategy.

I had a dumb script — curl the bot every few minutes, fire a Telegram webhook if it didn't respond. Detection without recovery. I was the recovery.

2 AM. Telegram buzzes. *Botty not responding.* I'd roll over, SSH in, restart it, fall back asleep. Two hours later: *Workflow failed.* Same dance. Each fix took five minutes and felt like progress. It wasn't. I was a human retry loop.

The setup, if it helps: OpenClaw ([github.com/openclaw/openclaw](https://github.com/openclaw/openclaw)) runs locally on my Mac as a Telegram assistant (@botty_izzy_bot). It's the main agent — handles conversations, spawns scheduled workflows, does the day-to-day work. Model is qwen3.5:397b-cloud via Ollama Cloud API. On top of that, OpenClaw runs a handful of autonomous cron workflows that actually do things: flat-hunting in Berlin, morning briefings, email triage, newsletter-to-podcast. The failures were boring and repeatable — process crashes, version drift, workflows silently regressing. Nothing novel. Which made the 2 AM pages extra insulting.

At some point I noticed I hadn't shipped a feature in three weeks, and I got annoyed enough to actually fix it.

## The idea I almost got wrong

My first instinct was to give OpenClaw the ability to heal itself. Self-monitoring, self-restarting, the whole thing.

I'm glad I didn't. The obvious problem: if the main agent is the thing crashing, it's also the thing trying to fix the crash. That's not self-healing. That's a suicide pact.

So I split the ops layer out entirely. For the watchdog I brought in Hermes ([github.com/nousresearch/hermes](https://github.com/nousresearch/hermes)) — a separate open-source agent (Nous Research's architecture, my own deployment) — and pointed it at OpenClaw with one job: *keep OpenClaw alive, and tell me when OpenClaw is slipping.*

Different agent. Different process. Different purpose. When OpenClaw dies, Hermes is still breathing. That's the one design decision I'd defend to anyone. Everything else I'm less sure about.

## What Hermes actually does

Two things, at very different tempos.

**Every 5 minutes:** a boring Python script. Hermes's moment-to-moment watchdog is `botty_health_monitor.py`, scheduled by macOS launchd. No LLM calls. No clever reasoning. Just:

1. Ping OpenClaw's process
2. Check installed version against the latest GitHub release
3. Auto-update if behind
4. Restart if crashed or unresponsive
5. Log results; Telegram me only if something's actually broken

This deliberately isn't an AI task. At a 5-minute cadence the whole point is to be cheap, deterministic, and almost impossible to break. If I'd wired an LLM into this loop I'd be paying tokens to do what a dozen lines of Python can do perfectly. Boring beats clever here.

**Daily:** an LLM-judge eval. This is the part that earns Hermes its keep. Once a day, Hermes runs 35 test cases across 8 quality dimensions against OpenClaw's recent behavior and scores each one. The judge model is gemma4:31b-cloud — I started with qwen3.5 but it kept timing out.

Current pass rate: 51%. Eighteen out of thirty-five.

That number is bad. It's also the most valuable number in my system.

Before the eval, I had *vibes.* I thought OpenClaw was doing fine. The eval showed me that on this specific test set it's passing about half the time. Now I see regressions within 24 hours instead of finding out weeks later when a workflow silently starts producing garbage. I can target prompt fixes. I can tell whether a model swap actually helped.

Running evals on your own agent is the highest-leverage thing I've done in months. Watching the number be embarrassing is the price of having honest information.

## The observability layer I didn't know I needed

ClawLens ([github.com/iiizzzyyy/clawlens](https://github.com/iiizzzyyy/clawlens)) tracks every agent session — tokens, costs, errors, tool calls, timelines. Before this, I was flying blind between daily evals. Now I see:

- Which agents are actually running (vs. silently crashed)
- Token usage per agent per hour
- Error patterns before they become outages
- Cron job success/failure rates

The health monitor queries ClawLens hourly and Telegrams me only when something's actually wrong. Zero noise, all signal.

Here's what this week's report looked like:

![ClawLens Health Report Example](assets/telegram-report-example.png)

*Actual Telegram alert from the hourly health monitor — sent to @botty_izzy_bot*

The 2M+ tokens? That's the sum of input + output across 6 sessions in one hour. The breakdown shows `main` driving 96% of usage — heavy reasoning tasks, large context prompts. Before ClawLens, I had no idea.

## What OpenClaw does once it stays up

Reliability only matters if the agent is doing useful work. OpenClaw runs a small fleet of scheduled workflows:

- **Morning briefing, 7 AM.** Calendar, tasks, weather → one digest message.
- **Email triage, 3x daily.** Fetch, categorize, summarize.
- **Berlin rental monitoring, 3x daily.** Scrapes listings, alerts on anything new that matches my filters. (If you've apartment-hunted in Berlin, you understand.)
- **Blog promotion, 8 AM & 5 PM.** Drafts promo content, sends it to me for review.
- **Newsletter-to-podcast, 10 PM.** Converts long-form reads into audio I listen to while walking.
- **Stretch reminders, 10 AM / 2 PM / 4 PM.** Honestly? Life-changing.

None of these are groundbreaking individually. The point is that they run unattended for months, because Hermes keeps OpenClaw alive and honest.

## The design principle I keep coming back to

**Match the tool to the frequency.**

| Frequency | Tool | Why |
|-----------|------|-----|
| Every 5 min | Python script | Cheap, deterministic, nothing to break |
| Every hour | API queries + patterns | Fast observability, no LLM cost |
| Every day | LLM judge | Expensive but catches nuanced regressions |
| Novel incidents | Human | Only I can reason about new failure shapes |

Each layer is the right tool for its rhythm. An LLM in the 5-minute loop would burn tokens on a task with a perfect scripted solution. A script in the eval loop wouldn't catch the things that actually regress — tone, coherence, whether the agent is hallucinating tools. And a human in either of them is just being a retry loop again.

## Where self-healing doesn't work

It handles failures it's seen before. That's the whole trick and the whole limitation.

Transient stuff — process crashes, version drift, memory bloat — the launchd watchdog handles fine. Predictable workflow failures with retry-once, mostly fine. The daily eval catches slow quality regressions.

What doesn't work, and I think this is structural: anything requiring judgment. Breaking API changes. Security incidents. Data corruption. First-time failures. I tried letting Hermes take broader "figure out what went wrong" actions and it confidently applied fixes from adjacent patterns that didn't apply. I pulled that back fast.

The rule I landed on: scripts handle known-shape failures. Hermes watches and evaluates. I handle anything novel. No "figure it out" mode. Not yet, maybe not ever.

## Things I'd tell myself six months ago

**Separate the ops agent from the main agent.** If one crashes, the other should still be running. Obvious in retrospect. I wasted two weeks before I accepted it.

**Don't AI-up the high-frequency loop.** The 5-minute ping doesn't need a model. The daily eval does. Match tool to tempo.

**Write the playbook before you automate it.** If I can't describe the fix in six steps, Hermes shouldn't be doing it. Automation is just faster execution of a thing I already trust.

**Evaluate your agent, even when it's embarrassing.** A 51% pass rate looks worse than "I think it's probably fine." It's also actually true, and that's the whole point.

**The insight that changed everything:** reliability isn't about preventing failures. It's about reducing time-to-detection and time-to-recovery. My 5-minute script catches crashes in 300 seconds instead of 3 days. The daily eval catches quality regressions in 24 hours instead of 3 weeks. That's the whole game. Everything else is implementation.

## Why I actually care about this

Not for the recovered engineer time, though sure.

The real thing: I'm building an AI-native company, and the hard part isn't the model calls. It's everything around them. Delivery infrastructure for AI products is not solved. You cannot run this the way you ran a CRUD app. Agents fail in new shapes. Observability is half-invented. Most production AI deployments I see are one weird outage away from losing their founder a weekend.

I think the teams that figure out the operational layer will outship everyone else by a wide margin. Not because their models are better — because their models actually run. Reliability compounds. A system that heals itself at 2 AM and evaluates itself at 6 AM is a team that ships on Monday.

I'm still figuring this out. I don't know if this is the right shape long-term or if I'll look at this post in a year and wince. Probably both. But I'd rather be publicly wrong and iterating than quietly tired.

If you're building on top of agents and still living inside your pager, I'd love to hear what's breaking for you. The failure modes are where the interesting work is.

---

## Want to replicate this?

![OpenClaw Self-Healing Architecture](assets/architecture-diagram.png)

*System architecture: Three-layer monitoring with separate ops agent (Hermes) watching the main agent (OpenClaw)*

**All scripts are open-source:** [github.com/iiizzzyyy/openclaw-ops](https://github.com/iiizzzyyy/openclaw-ops)

MIT licensed — fork it, adapt it, break it, fix it. Includes:

- `botty_health_monitor.py` — 5-minute watchdog (launchd)
- `llm_judge_eval.py` — Daily LLM judge evaluation
- `clawlens_health_monitor.py` — Hourly health monitoring
- Complete setup docs + troubleshooting guide

**Setup time:** ~1 hour  
**Time saved:** 5-7 hours/week (no more 2 AM pages)

---

*Izzy builds PromptMetrics — EU-first LLM observability for engineering teams. Next week: the Hive Architecture — how specialized subagents coordinate under one dispatcher. Subscribe if you're in the weeds on multi-agent systems.*
