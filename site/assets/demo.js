/* The live demo: real engine, seeded data, nothing leaves the tab.
 *
 * State is kept in localStorage so approving a draft and reloading the page does
 * not lose the thread. "Reset demo" puts the six invented businesses back.
 */
(function () {
  "use strict";

  var Engine = window.OttoEngine;
  var STORAGE_KEY = "otto.demo.v2";
  var config = Engine.DEFAULT_CONFIG;

  /* The same six businesses as otto/demo.py, on reserved .test domains. */
  var SNAPSHOTS = {
    "northlinephysio.test": {
      title: "Northline Physio | Sports injury rehab",
      description: "Rehabilitation for runners and cyclists, with gait analysis on site.",
      headings: ["Gait analysis"],
      paragraphs: ["We run six clinics a week and lose a third of them to no-shows."]
    },
    "cedarlanegarage.test": {
      title: "Cedar Lane Garage",
      description: "Servicing and MOT prep for family cars, loan car available.",
      headings: ["Book a service"],
      paragraphs: ["Most of our bookings come through WhatsApp messages that nobody answers until lunch."]
    }
  };

  var SEED = [
    {
      name: "Harbor Dental Studio",
      domain: "harbordental.test",
      email: "hello@harbordental.test",
      city: "Karachi",
      category: "dentist",
      status: "profiled",
      facts: {
        title: "Harbor Dental Studio | Family dentistry in Clifton",
        description: "Same-week appointments, evening slots and a hygiene plan for families.",
        headings: ["Evening appointments", "Hygiene plans"],
        paragraphs: ["We keep two evening slots open every day for people who cannot take time off work."]
      }
    },
    {
      name: "Highline Roofing",
      domain: "highlineroofing.test",
      email: "office@highlineroofing.test",
      city: "Karachi",
      category: "roofer",
      status: "profiled",
      facts: {
        title: "Highline Roofing",
        description: "Flat roof repairs and waterproofing for commercial buildings since 1998.",
        headings: ["Waterproofing", "Emergency repairs"],
        paragraphs: ["We answer emergency calls within four hours, seven days a week."]
      }
    },
    {
      name: "Phoenix HVAC",
      domain: "phoenixhvac.test",
      email: "dispatch@phoenixhvac.test",
      city: "Karachi",
      category: "hvac",
      status: "profiled",
      facts: {
        title: "Phoenix HVAC - installation and servicing",
        description: "Commercial air conditioning installs, plus a maintenance contract that includes two services a year.",
        headings: ["Maintenance contracts"],
        paragraphs: ["Our dispatcher books every job from a paper diary and two phone lines."]
      }
    },
    {
      name: "Terrace Bistro",
      domain: "terracebistro.test",
      email: "team@terracebistro.test",
      city: "Lahore",
      category: "restaurant",
      status: "profiled",
      facts: {
        title: "Terrace Bistro",
        description: "A twenty seat room, a short menu that changes weekly, walk-ins welcome.",
        headings: ["This week's menu"],
        paragraphs: ["We take reservations by phone only, from eleven in the morning."]
      }
    },
    {
      name: "Northline Physio",
      domain: "northlinephysio.test",
      email: "reception@northlinephysio.test",
      city: "Islamabad",
      category: "physiotherapist",
      status: "new",
      facts: null
    },
    {
      name: "Cedar Lane Garage",
      domain: "cedarlanegarage.test",
      email: "workshop@cedarlanegarage.test",
      city: "Karachi",
      category: "car_repair",
      status: "new",
      facts: null
    }
  ];

  function nowIso() {
    return new Date().toISOString().replace(/\.\d+Z$/, "Z");
  }

  function seedState() {
    return {
      clock: nowIso(),
      nextDraftId: 1,
      prospects: SEED.map(function (p, i) {
        return {
          id: i + 1,
          name: p.name,
          domain: p.domain,
          email: p.email,
          city: p.city,
          category: p.category,
          status: p.status,
          facts: p.facts
        };
      }),
      drafts: [],
      replies: [],
      events: []
    };
  }

  var state = load();

  function load() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && parsed.prospects && parsed.prospects.length) return parsed;
      }
    } catch (err) {
      /* private mode, or bad JSON: fall through to a fresh seed */
    }
    return seedState();
  }

  function save() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (err) {
      /* storage is a nicety, not a requirement */
    }
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function prospectOf(id) {
    return state.prospects.filter(function (p) { return p.id === id; })[0] || null;
  }

  var tab = "outbox";
  var expanded = {};

  /* --- rendering ---------------------------------------------------------- */

  function setText(selector, value) {
    var node = document.querySelector(selector);
    if (node) node.textContent = value;
  }

  function renderStats() {
    var c = Engine.counts(state);
    setText('[data-stat="prospects"]', state.prospects.length);
    setText('[data-stat="unprofiled"]', c.unprofiled);
    setText('[data-stat="awaiting_approval"]', c.awaiting_approval);
    setText('[data-stat="approved"]', c.approved);
    setText('[data-stat="decision"]', Engine.decide(c));

    var chips = { draft: c.awaiting_approval, approved: c.approved };
    chips.sent = state.drafts.filter(function (d) { return d.status === "sent"; }).length;
    chips.replies = state.replies.length;
    Object.keys(chips).forEach(function (key) {
      var node = document.querySelector('[data-chip="' + key + '"]');
      if (node) node.textContent = chips[key];
    });

    var decision = Engine.decide(c);
    document.querySelectorAll("#priority-list li").forEach(function (li) {
      li.classList.toggle("is-active", li.getAttribute("data-priority") === decision);
    });
  }

  function draftCard(draft) {
    var prospect = prospectOf(draft.prospectId) || { name: "unknown", email: "", domain: "" };
    var open = !!expanded[draft.id];
    var kindLabel = draft.kind === "reply" ? "reply" : "outreach";
    var actions = "";

    if (draft.status === "draft") {
      actions =
        '<button class="btn btn-sm btn-peach" data-approve="' + draft.id + '">Approve</button>' +
        '<button class="btn btn-sm btn-ghost" data-skip="' + draft.id + '">Skip</button>';
    } else if (draft.status === "approved") {
      actions = '<span class="tag">waiting for next cycle</span>';
    } else if (draft.status === "sent") {
      actions = '<span class="tag">sent · ' + esc(draft.delivery || "dry_run") + "</span>";
    } else if (draft.status === "skipped") {
      actions = '<span class="tag">skipped · ' + esc(draft.error || "") + "</span>";
    }

    return (
      '<article class="draft">' +
      '<div class="draft-head">' +
      '<span class="draft-to">' + esc(prospect.name) + " · " + esc(prospect.email || "no address") + "</span>" +
      '<span><span class="draft-kind ' + (draft.kind === "reply" ? "is-reply" : "") + '">' + kindLabel + "</span></span>" +
      "</div>" +
      '<div class="draft-subject">' + esc(draft.subject) + "</div>" +
      '<pre class="draft-body ' + (open ? "is-open" : "") + '">' + esc(draft.body) + "</pre>" +
      '<div class="draft-actions">' +
      actions +
      '<button class="more" data-toggle="' + draft.id + '">' + (open ? "Show less" : "Show full email") + "</button>" +
      "</div></article>"
    );
  }

  function emptyState(title, body) {
    return '<div class="empty"><div><b>' + esc(title) + "</b>" + esc(body) + "</div></div>";
  }

  function panelOutbox() {
    var rows = state.drafts.filter(function (d) { return d.status === "draft"; });
    if (!rows.length) {
      return emptyState("Outbox is empty", "Press “Run one cycle” and the writer will fill it.");
    }
    return rows.map(draftCard).join("");
  }

  function panelApproved() {
    var rows = state.drafts.filter(function (d) { return d.status === "approved"; });
    if (!rows.length) return emptyState("Nothing approved", "Approve a draft in the outbox to queue it.");
    return rows.map(draftCard).join("");
  }

  function panelSent() {
    var rows = state.drafts.filter(function (d) { return d.status === "sent"; });
    if (!rows.length) return emptyState("Nothing sent yet", "This demo runs in dry-run mode, so sends are logged, not delivered.");
    return rows
      .map(function (d) {
        var prospect = prospectOf(d.prospectId) || {};
        return (
          '<div class="rowline"><span><strong>' + esc(prospect.name || "unknown") + "</strong> · " +
          esc(d.subject) + "</span><span>" + esc((d.sentAt || "").slice(11, 16)) +
          ' · <span class="tag">' + esc(d.delivery || "dry_run") + "</span></span></div>"
        );
      })
      .join("");
  }

  function panelReplies() {
    var list = state.replies
      .map(function (r) {
        var prospect = prospectOf(r.prospectId) || {};
        var cls = r.classification;
        var tagClass = cls === "interested" ? "tag-int" : cls === "objection" ? "tag-obj" : cls === "unsubscribe" ? "tag-out" : "";
        return (
          '<article class="draft">' +
          '<div class="draft-head"><span class="draft-to">' + esc(prospect.name || "unknown prospect") +
          "</span><span class=\"tag " + tagClass + '">' + esc(cls) + "</span></div>" +
          '<div class="draft-subject">' + esc(r.subject) + "</div>" +
          '<pre class="draft-body is-open">' + esc(r.body) + "</pre>" +
          "</article>"
        );
      })
      .join("");

    var controls =
      '<div class="draft-actions" style="padding:0 0 14px">' +
      '<span class="tag">simulate a reply:</span>' +
      '<button class="btn btn-sm" data-reply="interested">interested</button>' +
      '<button class="btn btn-sm" data-reply="objection">too expensive</button>' +
      '<button class="btn btn-sm" data-reply="unsubscribe">unsubscribe</button>' +
      "</div>";

    return controls + (list || emptyState("No conversations", "Simulate one above and watch the classifier work."));
  }

  function panelLog() {
    if (!state.events.length) return emptyState("Log is empty", "Every action Otto takes is recorded here.");
    return state.events
      .map(function (e) {
        return (
          '<div class="rowline"><span><strong>' + esc(e.kind) + "</strong> " + esc(e.detail) +
          "</span><span>" + esc(String(e.at).slice(11, 16)) + "</span></div>"
        );
      })
      .join("");
  }

  var PANELS = {
    outbox: panelOutbox,
    approved: panelApproved,
    sent: panelSent,
    replies: panelReplies,
    log: panelLog
  };

  function renderPanel() {
    var node = document.getElementById("demo-panel");
    if (!node) return;
    node.innerHTML = PANELS[tab]();
    node.setAttribute("aria-labelledby", "tab-" + tab);
  }

  function render() {
    renderStats();
    renderPanel();
    save();
  }

  /* --- toast -------------------------------------------------------------- */

  var toastTimer = null;
  function toast(message) {
    var node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      node.classList.remove("is-visible");
    }, 2400);
  }

  /* --- actions ------------------------------------------------------------ */

  function advanceClock(minutes) {
    var time = new Date(state.clock);
    time.setUTCMinutes(time.getUTCMinutes() + minutes);
    state.clock = time.toISOString().replace(/\.\d+Z$/, "Z");
  }

  function runCycle() {
    advanceClock(2);
    var result = Engine.cycle(state, config, SNAPSHOTS);
    render();
    var summary = result.steps.map(function (s) { return s.text; }).join(" · ");
    toast(result.action + " — " + summary);
  }

  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-approve],[data-skip],[data-toggle],[data-tab],[data-reply],#run-cycle,#reset-demo");
    if (!target) return;

    if (target.id === "run-cycle") return runCycle();

    if (target.id === "reset-demo") {
      state = seedState();
      expanded = {};
      tab = "outbox";
      document.querySelectorAll("[data-tab]").forEach(function (btn) {
        btn.setAttribute("aria-selected", String(btn.getAttribute("data-tab") === "outbox"));
      });
      render();
      toast("Demo reset to six fresh prospects");
      return;
    }

    var tabName = target.getAttribute("data-tab");
    if (tabName) {
      tab = tabName;
      document.querySelectorAll("[data-tab]").forEach(function (btn) {
        btn.setAttribute("aria-selected", String(btn === target));
      });
      renderPanel();
      return;
    }

    var approve = target.getAttribute("data-approve");
    if (approve) {
      var draft = state.drafts.find(function (d) { return d.id === Number(approve); });
      if (draft) {
        draft.status = "approved";
        var prospect = prospectOf(draft.prospectId);
        if (prospect) prospect.status = "approved";
        state.events.unshift({ kind: "approved", detail: "draft " + draft.id, at: state.clock });
        render();
        toast("Approved. Press “Run one cycle” to send it.");
      }
      return;
    }

    var skip = target.getAttribute("data-skip");
    if (skip) {
      var skipped = state.drafts.find(function (d) { return d.id === Number(skip); });
      if (skipped) {
        skipped.status = "skipped";
        skipped.error = "skipped by you";
        state.events.unshift({ kind: "skipped", detail: "draft " + skipped.id, at: state.clock });
        render();
        toast("Skipped. Nothing will be sent to them.");
      }
      return;
    }

    var toggle = target.getAttribute("data-toggle");
    if (toggle) {
      var id = Number(toggle);
      expanded[id] = !expanded[id];
      renderPanel();
      return;
    }

    var kind = target.getAttribute("data-reply");
    if (kind) {
      var candidate = state.prospects.find(function (p) {
        return state.drafts.some(function (d) {
          return d.prospectId === p.id && d.status === "sent";
        });
      }) || state.prospects[0];
      var bodies = {
        interested: "Thanks for the note. We lose a lot of evening bookings to no-shows. What does it cost per month, and can we try it on one chair first?",
        objection: "This looks too expensive for us right now, and we already use a paper diary. Maybe next quarter.",
        unsubscribe: "Please take me off this list, not interested."
      };
      var subject = "Re: " + config.product.name + " for " + candidate.name;
      state.replies.unshift({
        id: state.replies.length + 1,
        prospectId: candidate.id,
        subject: subject,
        body: bodies[kind],
        classification: Engine.classify(subject, bodies[kind]),
        handled: false
      });
      candidate.status = "replied";
      render();
      toast("Reply classified as “" + Engine.classify(subject, bodies[kind]) + "”. Run a cycle to answer it.");
    }
  });

  render();
})();
