/**
 * analyse-lead.mjs
 * Receives property analysis lead form submissions from /analyse-your-home.
 * Stores in system_monitor.analyse_leads AND system_monitor.leads (canonical).
 * Sends Telegram notification + Gmail notification to Will + confirmation email to the lead.
 * Returns lead_id for PostHog event tracking.
 * No auth required — public-facing form endpoint.
 */

import { MongoClient } from "mongodb";

let _client = null;
async function getClient() {
  if (!_client) {
    _client = new MongoClient(process.env.COSMOS_CONNECTION_STRING);
    await _client.connect();
  }
  return _client;
}

// ---------------------------------------------------------------------------
// Telegram notification to Will
// ---------------------------------------------------------------------------
async function notifyTelegram(lead) {
  try {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;
    if (!token || !chatId) {
      console.warn("Telegram: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID");
      return;
    }

    const sellLabel = lead.sell_timeline
      ? `Sell: ${lead.sell_timeline}`
      : "Sell: not specified";
    const buyLabel = lead.buy_timeline
      ? `Buy: ${lead.buy_timeline}`
      : "Buy: not specified";

    const text = [
      `\u{1F3E0} New Property Analysis Lead`,
      ``,
      `Name: ${lead.name}`,
      `Email: ${lead.email}`,
      `Phone: ${lead.phone}`,
      `Address: ${lead.address}`,
      ``,
      `${sellLabel}`,
      `${buyLabel}`,
      ``,
      `Source: /analyse-your-home`,
      `Time: ${lead.submitted_at}`,
    ].join("\n");

    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
    });

    if (res.ok) {
      console.log("Telegram: analyse lead notification sent");
    } else {
      console.error("Telegram notification failed:", res.status, await res.text());
    }
  } catch (err) {
    console.error("Telegram notification error:", err.message);
  }
}

// ---------------------------------------------------------------------------
// Gmail API helpers
// ---------------------------------------------------------------------------
async function getGmailAccessToken() {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.GMAIL_CLIENT_ID,
      client_secret: process.env.GMAIL_CLIENT_SECRET,
      refresh_token: process.env.GMAIL_REFRESH_TOKEN,
      grant_type: "refresh_token",
    }),
  });
  const data = await res.json();
  return data.access_token;
}

function buildRawEmail(from, to, subject, body, replyTo) {
  const headers = [
    `From: ${from}`,
    `To: ${to}`,
    ...(replyTo ? [`Reply-To: ${replyTo}`] : []),
    `Subject: ${subject}`,
    `Content-Type: text/plain; charset=utf-8`,
    ``,
    body,
  ].join("\r\n");

  return btoa(unescape(encodeURIComponent(headers)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function sendGmail(accessToken, raw) {
  return fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ raw }),
  });
}

// ---------------------------------------------------------------------------
// Notification to Will (email)
// ---------------------------------------------------------------------------
async function notifyWill(lead) {
  try {
    const accessToken = await getGmailAccessToken();
    if (!accessToken) return;

    const sender = process.env.GMAIL_SENDER_EMAIL;
    const subject = `New Property Analysis Lead: ${lead.name} \u2014 ${lead.address}`;

    const body = [
      `New lead from /analyse-your-home.`,
      ``,
      `Name:         ${lead.name}`,
      `Email:        ${lead.email}`,
      `Phone:        ${lead.phone}`,
      `Address:      ${lead.address}`,
      `Property:     ${lead.property_type} \u2014 ${lead.bedrooms}bd / ${lead.bathrooms}ba`,
      `Buy timeline: ${lead.buy_timeline}`,
      `Sell timeline: ${lead.sell_timeline}`,
      `Notes:        ${lead.notes || "(none)"}`,
      ``,
      `Source:       ${lead.source}`,
      `Referrer:     ${lead.referring_property || "direct"}`,
      ``,
      `---`,
      `Submitted: ${lead.submitted_at}`,
      `Stored in: system_monitor.analyse_leads + system_monitor.leads`,
    ].join("\n");

    const raw = buildRawEmail(
      `Fields Estate <${sender}>`,
      "will@fieldsestate.com.au",
      subject,
      body
    );
    const res = await sendGmail(accessToken, raw);
    if (res.ok) {
      console.log("Gmail: analyse lead notification sent");
    } else {
      console.error("Gmail notification failed:", res.status, await res.text());
    }
  } catch (err) {
    console.error("Gmail notification error:", err.message);
  }
}

// ---------------------------------------------------------------------------
// Confirmation email to the lead
// ---------------------------------------------------------------------------
async function sendConfirmation(lead) {
  try {
    const accessToken = await getGmailAccessToken();
    if (!accessToken) return;

    const sender = process.env.GMAIL_SENDER_EMAIL;
    const firstName = lead.name.split(" ")[0];

    const body = [
      `Hi ${firstName},`,
      ``,
      `Thanks for requesting a property analysis. I've received your details for ${lead.address} and will be in touch within 24 hours with a structured position report.`,
      ``,
      `This isn't an automated estimate \u2014 I'll analyse comparable sales, current buyer demand, and market conditions specific to your property.`,
      ``,
      `In the meantime, you can explore the analysis system we've built:`,
      `https://fieldsestate.com.au/for-sale`,
      ``,
      `If you have questions before we connect, just reply to this email.`,
      ``,
      `Will Simpson`,
      `Fields Estate`,
      `will@fieldsestate.com.au`,
      `https://fieldsestate.com.au`,
    ].join("\n");

    const raw = buildRawEmail(
      `Will Simpson <${sender}>`,
      lead.email,
      `Your property analysis request \u2014 ${lead.address}`,
      body,
      "will@fieldsestate.com.au"
    );
    const res = await sendGmail(accessToken, raw);
    if (res.ok) {
      console.log("Gmail: confirmation sent to", lead.email);
    } else {
      console.error("Gmail confirmation failed:", res.status);
    }
  } catch (err) {
    console.error("Gmail confirmation error:", err.message);
  }
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------
export default async (req) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const data = await req.json();

    // Honeypot
    if (data["bot-field"]) {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Validate required fields
    const required = ["name", "email", "phone", "address"];
    for (const field of required) {
      if (!data[field] || !data[field].trim()) {
        return new Response(
          JSON.stringify({ error: `Missing required field: ${field}` }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(data.email.trim())) {
      return new Response(
        JSON.stringify({ error: "Please enter a valid email address." }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const now = new Date().toISOString();
    const email = data.email.trim().toLowerCase();

    // Build lead document
    const lead = {
      name: data.name.trim(),
      email,
      phone: data.phone.trim(),
      address: data.address.trim(),
      property_type: data.property_type || null,
      bedrooms: data.bedrooms || null,
      bathrooms: data.bathrooms || null,
      buy_timeline: data.buy_timeline || null,
      sell_timeline: data.sell_timeline || null,
      notes: data.notes ? data.notes.trim() : null,
      source: data.source || "analyse_your_home",
      referring_property: data.referring_property || null,
      referring_suburb: data.referring_suburb || null,
      submitted_at: now,
      submitted_at_date: new Date(),
      status: "new",
    };

    // Save to MongoDB
    const client = await getClient();
    const db = client.db("system_monitor");

    // 1. Write to analyse_leads (detailed collection)
    const result = await db.collection("analyse_leads").insertOne(lead);

    // 2. Write to canonical leads collection (matching price-alert-subscribe pattern)
    const existingLead = await db.collection("leads").findOne({
      email,
      source: "analyse_your_home",
      address: data.address.trim(),
    });

    let canonicalLeadId = result.insertedId.toString();

    if (!existingLead) {
      const canonicalResult = await db.collection("leads").insertOne({
        email,
        name: data.name.trim(),
        phone: data.phone.trim(),
        source: "analyse_your_home",
        address: data.address.trim(),
        property_type: data.property_type || null,
        suburb: data.referring_suburb || null,
        buy_timeline: data.buy_timeline || null,
        sell_timeline: data.sell_timeline || null,
        status: "new",
        owner: "will",
        notes: "",
        first_response_at: null,
        next_action_at: null,
        lead_quality: null,
        created_at: now,
        created_at_date: new Date(),
      });
      canonicalLeadId = canonicalResult.insertedId.toString();
    } else {
      canonicalLeadId = existingLead._id.toString();
    }

    // Send notifications (non-blocking — fire all in parallel)
    Promise.all([
      notifyTelegram(lead),
      notifyWill(lead),
      sendConfirmation(lead),
    ]).catch(() => {});

    return new Response(
      JSON.stringify({ ok: true, lead_id: canonicalLeadId }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (err) {
    console.error("analyse-lead error:", err);
    return new Response(
      JSON.stringify({ error: "Something went wrong. Please try again." }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
};

export const config = {
  path: "/api/analyse-lead",
};
