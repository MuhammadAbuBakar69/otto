/* Otto's core logic, in the browser.
 *
 * This is a faithful port of otto/write.py, otto/replies.py, otto/send.py and
 * otto/pipeline.py. Same decision order, same template text, same guards. It
 * exists so the demo on the site runs the real logic instead of a video of it.
 *
 * What it cannot do: fetch prospect websites (CORS) or talk to a mail server.
 * Those two steps are marked where they happen.
 *
 * Plain ES2019, no build step, no dependencies. tests/site/engine.test.mjs
 * checks it against the Python implementation.
 */
(function (root) {
  "use strict";

  var PRIORITY = ["handle_replies", "send", "write", "profile", "idle"];

  var DEFAULT_CONFIG = {
    product: {
      name: "Bookwell",
      one_liner: "online booking for small service businesses",
      pitch:
        "We put your calendar, reminders and no-show follow-up in one place, " +
        "so the front desk stops chasing texts.",
      proof: "Shops on Bookwell cut no-shows by about a third in the first month.",
      cta: "Worth a 10 minute call next week?"
    },
    sender: { name: "Ayesha Khan", company: "Bookwell", postal_address: "12 Clifton Block 5, Karachi" },
    limits: { max_daily_drafts: 20, max_sends: 20 }
  };

  /* --- small helpers ------------------------------------------------------ */

  function normalizeDomain(value) {
    if (!value) return "";
    var text = String(value).trim().toLowerCase();
    if (text.indexOf("https://") === 0) text = text.slice(8);
    if (text.indexOf("http://") === 0) text = text.slice(7);
    text = text.split("/")[0].split("?")[0].split("#")[0];
    if (text.indexOf("www.") === 0) text = text.slice(4);
    if (text.indexOf("@") !== -1) text = text.split("@").pop();
    return text.replace(/^\.+|\.+$/g, "").trim();
  }

  var LEGAL = /\b(inc|ltd|llc|pvt|co|company|studio|clinic|shop|group)\b\.?/gi;

  function firstToken(name) {
    var cleaned = String(name || "").replace(LEGAL, "");
    var parts = cleaned.trim().split(/\s+/).filter(Boolean);
    return parts.length ? parts[0] : "there";
  }

  function bestDetail(facts) {
    facts = facts || {};
    var keys = ["description", "title"];
    for (var i = 0; i < keys.length; i++) {
      var value = String(facts[keys[i]] || "").trim();
      if (value.length >= 25 && value.length <= 240) return value.replace(/\.+$/, "");
    }
    var headings = facts.headings || [];
    for (var h = 0; h < headings.length; h++) {
      var heading = headings[h];
      if (heading.length >= 15 && heading.length <= 90) return heading.replace(/\.+$/, "");
    }
    var paragraphs = facts.paragraphs || [];
    for (var p = 0; p < paragraphs.length; p++) {
      var sentence = paragraphs[p].split(/(?<=[.!?])\s/)[0];
      if (sentence.length >= 25 && sentence.length <= 200) return sentence.replace(/\.+$/, "");
    }
    return "";
  }

  /* --- replies.py --------------------------------------------------------- */

  var OPT_OUT = /\b(unsubscribe|remove me|take me off|stop (emailing|contacting)|do not contact|don'?t contact|not interested|no thanks|no thank you|wrong person)\b/i;
  var INTERESTED = /\b(interested|tell me more|sounds good|let'?s talk|happy to chat|call me|schedule|book a (call|demo|time)|send (me )?(more|details|info)|yes please)\b/i;
  var OBJECTION = /\b(too expensive|price|pricing|cost|budget|already (use|have|work with)|not (right )?now|next (quarter|year)|too busy|contract)\b/i;

  function classify(subject, body) {
    var text = String(subject || "") + "\n" + String(body || "");
    if (OPT_OUT.test(text)) return "unsubscribe";
    if (INTERESTED.test(text)) return "interested";
    if (OBJECTION.test(text)) return "objection";
    if (text.indexOf("?") !== -1) return "question";
    return "other";
  }

  /* --- send.py ------------------------------------------------------------ */

  function footer(config) {
    var company = config.sender.company || config.product.name;
    var lines = ["--"];
    if (company) lines.push(company);
    if (config.sender.postal_address) lines.push(config.sender.postal_address);
    lines.push("Not relevant? Reply 'unsubscribe' and I will not write again.");
    return lines.join("\n");
  }

  function normalizeBody(config, body) {
    var text = String(body || "").trim();
    var tail = footer(config);
    if (text.slice(-tail.length) === tail) return text;
    return text + "\n\n" + tail;
  }

  /* --- write.py ----------------------------------------------------------- */

  function template(config, prospect, facts) {
    var product = config.product.name;
    var detail = bestDetail(facts);
    var city = prospect.city || "";
    var category = prospect.category || "business";

    var hook = "I came across " + prospect.name;
    if (city) hook += " while looking at " + category + " in " + city;
    hook += ".";

    var specificity = detail
      ? ' Your site says "' + detail + '" - that line stuck with me.'
      : " There is no marketing language on the site, which I liked.";

    var parts = [
      "Hi " + firstToken(prospect.name) + ",",
      "",
      hook + specificity,
      "",
      "I work on " + product + ", " + config.product.one_liner + ".",
      config.product.pitch,
      config.product.proof || "",
      "",
      config.product.cta,
      "",
      "- " + config.sender.name
    ];

    var body = parts.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    return { subject: (product + " for " + prospect.name).slice(0, 78), body: body };
  }

  var REPLY_OPENERS = {
    interested: function (name, config) {
      return (
        "Hi " + name + ",\n\n" +
        "Good to hear. Two slots that usually work: Tuesday morning or Thursday " +
        "afternoon. Tell me which is easier and I will send an invite.\n\n" +
        "If it helps first, I can send a two minute screen recording instead.\n\n" +
        "- " + config.sender.name
      );
    },
    objection: function (name, config) {
      return (
        "Hi " + name + ",\n\n" +
        "Fair. Most shops we work with said the same thing before they saw the " +
        "no-show numbers. Happy to send the one page breakdown, no call needed.\n\n" +
        "- " + config.sender.name
      );
    },
    question: function (name, config) {
      return (
        "Hi " + name + ",\n\n" +
        "Short answer: " + config.product.one_liner + ". " +
        "If you want the detail, I can send it over as a one pager.\n\n" +
        "- " + config.sender.name
      );
    },
    other: function (name, config) {
      return (
        "Hi " + name + ",\n\n" +
        "Thanks for coming back to me. Should I close the loop here, or is there " +
        "a better time later in the year?\n\n" +
        "- " + config.sender.name
      );
    }
  };

  function replySubject(reply, config) {
    var subject = String(reply.subject || config.product.name).trim();
    if (/^re:/i.test(subject)) return subject;
    return "Re: " + subject;
  }

  /* --- pipeline.py -------------------------------------------------------- */

  function counts(state) {
    var drafts = state.drafts || [];
    var prospects = state.prospects || [];
    var replies = state.replies || [];
    var byStatus = function (status, kind) {
      return drafts.filter(function (d) {
        return d.status === status && (!kind || d.kind === kind);
      }).length;
    };
    return {
      unhandled_replies: replies.filter(function (r) { return !r.handled; }).length,
      approved: byStatus("approved"),
      awaiting_approval: byStatus("draft"),
      unprofiled: prospects.filter(function (p) { return p.status === "new" && !p.facts; }).length,
      ready_to_write: prospects.filter(function (p) {
        return p.status === "profiled" && p.facts;
      }).length
    };
  }

  function decide(c) {
    if (c.unhandled_replies) return "handle_replies";
    if (c.approved) return "send";
    if (c.ready_to_write) return "write";
    if (c.unprofiled) return "profile";
    return "idle";
  }

  function hasOpenDraft(state, prospectId, kind) {
    return state.drafts.some(function (d) {
      return (
        d.prospectId === prospectId &&
        (!kind || d.kind === kind) &&
        (d.status === "draft" || d.status === "approved")
      );
    });
  }

  function log(state, kind, detail, prospectId) {
    state.events.unshift({
      kind: kind,
      detail: detail || "",
      at: state.clock,
      prospectId: prospectId || null
    });
    state.events = state.events.slice(0, 40);
  }

  function prospectOf(state, id) {
    return state.prospects.filter(function (p) { return p.id === id; })[0] || null;
  }

  function handleReplies(state, config) {
    var made = 0;
    state.replies.forEach(function (reply) {
      if (reply.handled) return;
      var prospect = prospectOf(state, reply.prospectId);
      reply.handled = true;
      if (reply.classification === "unsubscribe") {
        if (prospect) {
          prospect.status = "opted_out";
          state.drafts.forEach(function (d) {
            if (d.prospectId === prospect.id && d.status === "draft") {
              d.status = "skipped";
              d.error = "opted out";
            }
          });
        }
        log(state, "opted_out", prospect ? prospect.domain : "", prospect && prospect.id);
        return;
      }
      if (!prospect || hasOpenDraft(state, prospect.id, "reply")) return;
      var body = REPLY_OPENERS[reply.classification](firstToken(prospect.name), config);
      state.drafts.unshift({
        id: state.nextDraftId++,
        prospectId: prospect.id,
        kind: "reply",
        step: 1,
        subject: replySubject(reply, config),
        body: normalizeBody(config, body),
        status: "draft",
        createdAt: state.clock,
        delivery: "",
        error: ""
      });
      prospect.status = "replied";
      log(state, "reply_drafted", reply.classification, prospect.id);
      made += 1;
    });
    return made;
  }

  function sendApproved(state, config) {
    var sent = 0;
    var skipped = 0;
    var cap = config.limits.max_sends;
    var already = state.drafts.filter(function (d) {
      return d.status === "sent" && String(d.sentAt || "").slice(0, 10) === state.clock.slice(0, 10);
    }).length;
    var room = Math.max(0, cap - already);

    state.drafts.forEach(function (draft) {
      if (draft.status !== "approved" || sent >= room) return;
      var prospect = prospectOf(state, draft.prospectId);
      if (!prospect || prospect.status === "opted_out") {
        draft.status = "skipped";
        draft.error = "prospect opted out";
        skipped += 1;
        return;
      }
      if (!prospect.email) {
        draft.status = "skipped";
        draft.error = "no email address on file";
        skipped += 1;
        return;
      }
      draft.status = "sent";
      draft.delivery = "dry_run";
      draft.sentAt = state.clock;
      prospect.status = "sent";
      log(state, "sent", "dry_run", prospect.id);
      sent += 1;
    });
    return { sent: sent, skipped: skipped, room: room };
  }

  function writePending(state, config) {
    var cap = config.limits.max_daily_drafts;
    var draftedToday = state.drafts.filter(function (d) {
      return String(d.createdAt || "").slice(0, 10) === state.clock.slice(0, 10);
    }).length;
    var room = Math.max(0, cap - draftedToday);
    var made = 0;

    state.prospects.forEach(function (prospect) {
      if (made >= room) return;
      var eligible = (prospect.status === "profiled" || prospect.status === "new") && prospect.facts;
      if (!eligible || hasOpenDraft(state, prospect.id)) return;
      var made_ = template(config, prospect, prospect.facts);
      state.drafts.unshift({
        id: state.nextDraftId++,
        prospectId: prospect.id,
        kind: "outreach",
        step: 1,
        subject: made_.subject,
        body: normalizeBody(config, made_.body),
        status: "draft",
        createdAt: state.clock,
        delivery: "",
        error: ""
      });
      prospect.status = "drafted";
      log(state, "draft", "template", prospect.id);
      made += 1;
    });
    return made;
  }

  function profilePending(state, snapshots) {
    var made = 0;
    state.prospects.forEach(function (prospect) {
      if (prospect.status !== "new" || prospect.facts) return;
      var facts = (snapshots || {})[prospect.domain];
      if (!facts) return;
      prospect.facts = facts;
      prospect.status = "profiled";
      log(state, "profile", "captured snapshot", prospect.id);
      made += 1;
    });
    return made;
  }

  function cycle(state, config, snapshots) {
    var before = counts(state);
    var action = decide(before);
    var steps = [];

    var answered = handleReplies(state, config);
    if (answered) steps.push({ label: "handler", text: answered + " answer(s) drafted for approval" });

    var sending = sendApproved(state, config);
    if (sending.sent || sending.skipped) {
      steps.push({
        label: "outbox",
        text: sending.sent + " sent, " + sending.skipped + " skipped (dry run)"
      });
    }

    var drafted = writePending(state, config);
    if (drafted) steps.push({ label: "writer", text: drafted + " draft(s) waiting for you" });

    var profiled = profilePending(state, snapshots);
    if (profiled) steps.push({ label: "reader", text: profiled + " profile(s) attached, $0" });

    if (!steps.length) steps.push({ label: "idle", text: "nothing to do. Add prospects to continue." });

    return { action: action, steps: steps, counts: counts(state) };
  }

  var api = {
    PRIORITY: PRIORITY,
    DEFAULT_CONFIG: DEFAULT_CONFIG,
    normalizeDomain: normalizeDomain,
    firstToken: firstToken,
    bestDetail: bestDetail,
    classify: classify,
    footer: footer,
    normalizeBody: normalizeBody,
    template: template,
    replySubject: replySubject,
    counts: counts,
    decide: decide,
    cycle: cycle
  };

  if (typeof module === "object" && module.exports) module.exports = api;
  else root.OttoEngine = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
