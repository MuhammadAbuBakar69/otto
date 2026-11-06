/* Parity and behaviour tests for the browser engine.
 *
 *   node --test tests/site/
 *
 * The interesting test is the first one: it runs the Python implementation and
 * the JavaScript one on the same input and requires identical bytes. If the two
 * drift, the site is lying about what the CLI does.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const Engine = require("../../site/assets/engine.js");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");

const CONFIG = Engine.DEFAULT_CONFIG;

const PROSPECT = {
  id: 1,
  name: "Harbor Dental Studio",
  domain: "harbordental.test",
  email: "hello@harbordental.test",
  city: "Karachi",
  category: "dentist",
  status: "profiled",
  facts: {
    title: "Harbor Dental Studio | Family dentistry in Clifton",
    description: "Same-week appointments, evening slots and a hygiene plan for families.",
    headings: ["Evening appointments"]
  }
};

const PYTHON = `
import json, sys
sys.path.insert(0, ".")
from otto import config, write, send, replies

cfg = config.load(".")
cfg.set("product.name", "Bookwell")
cfg.set("product.one_liner", "online booking for small service businesses")
cfg.set("product.pitch", "We put your calendar, reminders and no-show follow-up in one place, so the front desk stops chasing texts.")
cfg.set("product.proof", "Shops on Bookwell cut no-shows by about a third in the first month.")
cfg.set("product.cta", "Worth a 10 minute call next week?")
cfg.set("sender.name", "Ayesha Khan")
cfg.set("sender.company", "Bookwell")
cfg.set("sender.postal_address", "12 Clifton Block 5, Karachi")

prospects = [
    {"name": "Harbor Dental Studio", "domain": "harbordental.test", "city": "Karachi", "category": "dentist"},
    {"name": "Phoenix HVAC", "domain": "phoenixhvac.test", "city": "", "category": "hvac"},
]
facts = [
    {"title": "Harbor Dental Studio | Family dentistry in Clifton",
     "description": "Same-week appointments, evening slots and a hygiene plan for families.",
     "headings": ["Evening appointments"]},
    {},
]
out = []
for p, f in zip(prospects, facts):
    subject, body, _source = write.draft(cfg, p, f)
    out.append({"subject": subject, "body": send.normalize_body(cfg, body)})
out.append({"footer": send.footer(cfg)})
cases = [
    ("Re: hi", "Please take me off this list."),
    ("Re: hi", "Sounds good, can we book a call?"),
    ("Re: hi", "How much does this cost?"),
    ("Re: hi", "What does onboarding look like?"),
    ("Re: hi", "Thanks, noted."),
]
out.append({"classify": [replies.classify(s, b) for s, b in cases]})
print(json.dumps(out))
`;

test("drafts are byte-identical to the Python implementation", () => {
  const raw = execFileSync("python3", ["-c", PYTHON], {
    cwd: ROOT,
    env: { ...process.env, OTTO_MODEL_PROVIDER: "none" },
    encoding: "utf8"
  });
  const [withDetail, withoutDetail, footerBlock, classifyBlock] = JSON.parse(raw);

  const js1 = Engine.template(CONFIG, PROSPECT, PROSPECT.facts);
  const js2 = Engine.template(
    CONFIG,
    { name: "Phoenix HVAC", city: "", category: "hvac" },
    {}
  );

  assert.equal(js1.subject, withDetail.subject);
  assert.equal(Engine.normalizeBody(CONFIG, js1.body), withDetail.body);
  assert.equal(js2.subject, withoutDetail.subject);
  assert.equal(Engine.normalizeBody(CONFIG, js2.body), withoutDetail.body);
  assert.equal(Engine.footer(CONFIG), footerBlock.footer);

  const cases = [
    ["Re: hi", "Please take me off this list."],
    ["Re: hi", "Sounds good, can we book a call?"],
    ["Re: hi", "How much does this cost?"],
    ["Re: hi", "What does onboarding look like?"],
    ["Re: hi", "Thanks, noted."]
  ];
  assert.deepEqual(
    cases.map(([s, b]) => Engine.classify(s, b)),
    classifyBlock.classify
  );
});

test("normalizeDomain matches the CLI", () => {
  assert.equal(Engine.normalizeDomain("https://HarborDental.test/about?x=1"), "harbordental.test");
  assert.equal(Engine.normalizeDomain("http://www.example.com/"), "example.com");
  assert.equal(Engine.normalizeDomain("hello@northline.test"), "northline.test");
  assert.equal(Engine.normalizeDomain(""), "");
});

test("firstToken strips legal suffixes", () => {
  assert.equal(Engine.firstToken("Harbor Dental Studio"), "Harbor");
  assert.equal(Engine.firstToken("Cedar Lane Garage Ltd"), "Cedar");
  assert.equal(Engine.firstToken(""), "there");
});

test("decide follows the documented priority", () => {
  const cases = [
    [{ unhandled_replies: 1, approved: 3, ready_to_write: 2, unprofiled: 5 }, "handle_replies"],
    [{ unhandled_replies: 0, approved: 3, ready_to_write: 2, unprofiled: 5 }, "send"],
    [{ unhandled_replies: 0, approved: 0, ready_to_write: 2, unprofiled: 5 }, "write"],
    [{ unhandled_replies: 0, approved: 0, ready_to_write: 0, unprofiled: 5 }, "profile"],
    [{ unhandled_replies: 0, approved: 0, ready_to_write: 0, unprofiled: 0 }, "idle"]
  ];
  for (const [counts, expected] of cases) assert.equal(Engine.decide(counts), expected);
});

function state(prospects, drafts = [], replies = []) {
  return {
    clock: "2026-11-06T09:00:00Z",
    nextDraftId: 100,
    prospects,
    drafts,
    replies,
    events: []
  };
}

test("an opt-out cancels their pending draft and blocks sending", () => {
  const s = state(
    [{ ...PROSPECT, status: "replied" }],
    [{ id: 1, prospectId: 1, kind: "outreach", subject: "Hi", body: "Body", status: "approved" }],
    [{ id: 1, prospectId: 1, subject: "Re: hi", body: "Not interested, remove me.", classification: "unsubscribe", handled: false }]
  );
  Engine.cycle(s, CONFIG, {});
  assert.equal(s.prospects[0].status, "opted_out");
  assert.equal(s.drafts[0].status, "skipped");
  // handle_replies cancels queued drafts; send_approved catches anything
  // already approved. Both end with the draft dead and the reason recorded.
  assert.match(s.drafts[0].error, /opted out/);
});

test("a reply becomes a draft answer and never double-Re", () => {
  const s = state(
    [{ ...PROSPECT, status: "replied" }],
    [],
    [{ id: 1, prospectId: 1, subject: "Re: Bookwell for Harbor", body: "Tell me more", classification: "interested", handled: false }]
  );
  const result = Engine.cycle(s, CONFIG, {});
  assert.equal(result.action, "handle_replies");
  const replyDraft = s.drafts.find((d) => d.kind === "reply");
  assert.ok(replyDraft);
  assert.equal(replyDraft.subject, "Re: Bookwell for Harbor");
  assert.match(replyDraft.body, /^Hi Harbor,/);
});

test("approved drafts send in dry-run and update the prospect", () => {
  const s = state(
    [{ ...PROSPECT, status: "approved" }],
    [{ id: 1, prospectId: 1, kind: "outreach", subject: "Hi", body: "Body", status: "approved" }]
  );
  const result = Engine.cycle(s, CONFIG, {});
  assert.equal(result.action, "send");
  assert.equal(s.drafts[0].status, "sent");
  assert.equal(s.drafts[0].delivery, "dry_run");
  assert.equal(s.prospects[0].status, "sent");
});

test("a prospect with no email is skipped, never guessed", () => {
  const s = state(
    [{ ...PROSPECT, email: "", status: "approved" }],
    [{ id: 1, prospectId: 1, kind: "outreach", subject: "Hi", body: "Body", status: "approved" }]
  );
  Engine.cycle(s, CONFIG, {});
  assert.equal(s.drafts[0].status, "skipped");
  assert.match(s.drafts[0].error, /no email/);
});

test("the daily draft cap holds", () => {
  const config = { ...CONFIG, limits: { ...CONFIG.limits, max_daily_drafts: 1 } };
  const s = state([
    { ...PROSPECT, id: 1, status: "profiled" },
    { ...PROSPECT, id: 2, domain: "b.test", name: "Beta Roofing", status: "profiled" }
  ]);
  Engine.cycle(s, config, {});
  assert.equal(s.drafts.length, 1);
});
