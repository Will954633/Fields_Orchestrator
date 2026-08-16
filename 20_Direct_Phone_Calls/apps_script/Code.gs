/**
 * Code.gs — "☎ Call" sidebar for the Marketing Phone Calls sheet.
 *
 * WHAT IT IS
 *   A docked panel beside the grid. Select any call row; the panel shows that
 *   person's brief and one CALL button. The button opens JustCall's dialer in a
 *   small popup window — the spreadsheet stays visible and editable behind it,
 *   so notes go straight into the sheet during the call.
 *
 * WHY A SIDEBAR AND NOT A LINK IN THE CELL
 *   Google Sheets' HYPERLINK() only permits http/https/mailto/aim/ftp/gopher/
 *   telnet/news. A `tel:` link renders as unclickable plain text — it fails
 *   silently, which is the worst possible failure for a dial button. And an
 *   https link in a cell opens a full TAB, covering the sheet. A sidebar popup
 *   is the only shape that keeps the grid on screen.
 *
 * WHY NOT THE JUSTCALL API
 *   There is no API that places a call from your own device. The only outbound
 *   endpoint (initiate_outbound_call_v21) makes an AI Voice Agent talk to the
 *   person instead of you, and requires documented prior consent. It is not
 *   this feature. This sidebar uses JustCall's dialer deep link, which is a
 *   plain URL and needs no credentials — so no secret is ever stored in a
 *   spreadsheet that gets shared.
 *
 * THE COMPLIANCE GATE IS THE POINT
 *   This button makes dialling one click, so every reason NOT to dial has to be
 *   enforced at that click rather than remembered. The CALL button does not
 *   render at all unless the row passes:
 *     - DNC: column J shows a real wash date, never "NOT WASHED"          (DNCR s11(3))
 *     - Day/time inside the ACL s73 window                                (see CALLER_CARD.md §2)
 *     - Not a Sunday                                                      (Standard s8(1)(e))
 *     - Not a national public holiday                                     (Standard s8(3))
 *   A blocked row shows WHY, in words, instead of a button.
 *
 * THE metadata PARAMETER IS THE SECOND HALF OF THE FEATURE
 *   Every deep link carries the row's hidden Call ID (column Q) as `metadata`.
 *   JustCall relays it back in every webhook payload, so a call event arrives
 *   already knowing which row it belongs to. That replaces the fuzzy
 *   phone-digit join in justcall_sync.py, where an unmatched call is a fact
 *   the code cannot resolve.
 *
 * Install: see README.md in this folder.
 */

// ── Column positions, 1-based, mirroring HEADERS in scripts/sheet_common.py ──
// If that list ever changes, this must change with it. assertLayout() below
// checks the header row at load and refuses to run against a shifted sheet
// rather than reading the wrong column and dialling the wrong person.
var TAB = 'Call List';
var C = {
  callDate: 1, rank: 2, name: 3, phone: 4, address: 5, suburb: 6,
  whyNow: 7, track: 8, occupant: 9, dncWashed: 10, property: 11,
  outcome: 12, comments: 13, callback: 14,
  recording: 15, transcript: 16, callId: 17
};
var EXPECTED_HEADERS = {
  3: 'Name', 4: 'Phone', 10: 'DNC washed', 12: '☎ OUTCOME', 17: 'Call ID'
};

var TZ = 'Australia/Brisbane';

// ACL s73 — stricter than the ACMA Standard, therefore governs.
// Mirrors 01_Compliance/CALLER_CARD.md §2. Keep the two in step.
var HOURS = {
  1: [9, 18], 2: [9, 18], 3: [9, 18], 4: [9, 18], 5: [9, 18],  // Mon-Fri 9:00-18:00
  6: [9, 17],                                                   // Sat       9:00-17:00
  0: null                                                       // Sun       NEVER
};

// National (Commonwealth) public holidays — Standard s8(3) bans calling on
// these at ANY hour. QLD-only holidays are NOT in this list and are NOT caught;
// that gap is a known open decision (CALLER_CARD.md §123), not an oversight.
// A year missing from this table does not silently pass — see holidayStatus().
var NATIONAL_HOLIDAYS = {
  2026: ['01-01', '01-26', '04-03', '04-06', '04-25', '12-25', '12-26'],
  2027: ['01-01', '01-26', '03-26', '03-29', '04-25', '12-25', '12-26']
};


function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('☎ Calling')
    .addItem('Open call panel', 'showSidebar')
    .addToUi();
}

function showSidebar() {
  var html = HtmlService.createHtmlOutputFromFile('Sidebar')
    .setTitle('☎ Call panel')
    .setWidth(340);
  SpreadsheetApp.getUi().showSidebar(html);
}


// ─────────────────────────────────────────────────────────────────────────────
// Layout guard
// ─────────────────────────────────────────────────────────────────────────────
/**
 * Refuse to operate if the header row no longer matches the column map.
 *
 * The sheet is append-only and never rebuilt, but a human can still insert a
 * column. If that happened, every lookup below would silently shift by one and
 * the panel would offer to dial the number of a DIFFERENT person than the one
 * whose name it displays. That is the single worst thing this tool could do, so
 * it is checked rather than assumed.
 */
function assertLayout(sheet) {
  var width = sheet.getLastColumn();
  var header = sheet.getRange(1, 1, 1, Math.max(width, C.callId)).getValues()[0];
  for (var col in EXPECTED_HEADERS) {
    var got = String(header[Number(col) - 1] || '').trim();
    if (got !== EXPECTED_HEADERS[col]) {
      throw new Error(
        'Sheet layout has changed: column ' + colLetter(Number(col)) +
        ' should be "' + EXPECTED_HEADERS[col] + '" but reads "' + got + '". ' +
        'The call panel is disabled until the layout matches, because reading ' +
        'the wrong column here means dialling the wrong person. Fix the sheet, ' +
        'or update C{} in Code.gs and HEADERS in scripts/sheet_common.py together.');
    }
  }
}

function colLetter(n) {
  var s = '';
  while (n > 0) { var r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = (n - 1 - r) / 26; }
  return s;
}


// ─────────────────────────────────────────────────────────────────────────────
// Time / compliance
// ─────────────────────────────────────────────────────────────────────────────
function holidayStatus(now) {
  var year = Number(Utilities.formatDate(now, TZ, 'yyyy'));
  var md = Utilities.formatDate(now, TZ, 'MM-dd');
  var table = NATIONAL_HOLIDAYS[year];
  if (!table) {
    // Do NOT quietly allow. An unknown year is an unanswered question, and the
    // penalty for guessing wrong is a breach, so the caller answers it by hand.
    return { known: false, isHoliday: false, year: year };
  }
  return { known: true, isHoliday: table.indexOf(md) !== -1, year: year };
}

/**
 * Returns {ok, reason, needsHolidayConfirm} for dialling RIGHT NOW.
 * `reason` is written for a person mid-call, not for a log.
 */
function timeGate() {
  var now = new Date();
  var dow = Number(Utilities.formatDate(now, TZ, 'u')) % 7;  // 'u': 1=Mon..7=Sun -> 0=Sun
  var mins = Number(Utilities.formatDate(now, TZ, 'H')) * 60 +
             Number(Utilities.formatDate(now, TZ, 'm'));
  var clock = Utilities.formatDate(now, TZ, 'h:mm a EEE d MMM');

  var window_ = HOURS[dow];
  if (!window_) {
    return { ok: false, reason: 'It is Sunday (' + clock + '). Telemarketing ' +
             'Standard s8(1)(e) prohibits calling on a Sunday at any hour.' };
  }

  var hol = holidayStatus(now);
  if (hol.known && hol.isHoliday) {
    return { ok: false, reason: 'Today is a national public holiday. Standard ' +
             's8(3) prohibits calling at any hour.' };
  }

  if (mins < window_[0] * 60) {
    return { ok: false, reason: 'Too early — it is ' + clock + '. The window ' +
             'opens at ' + window_[0] + ':00 (ACL s73).' };
  }
  if (mins >= window_[1] * 60) {
    return { ok: false, reason: 'Too late — it is ' + clock + '. The window ' +
             'closed at ' + window_[1] + ':00 (ACL s73).' };
  }

  return {
    ok: true,
    clock: clock,
    closesAt: window_[1] + ':00',
    // Unknown year: allowed, but the caller must positively confirm rather than
    // the code assuming. The UI turns this into a checkbox in front of the button.
    needsHolidayConfirm: !hol.known,
    holidayNote: hol.known ? '' :
      'The public-holiday table does not cover ' + hol.year + '. Confirm by hand ' +
      'that today is not a national public holiday (Standard s8(3)), then extend ' +
      'NATIONAL_HOLIDAYS in Code.gs.'
  };
}


// ─────────────────────────────────────────────────────────────────────────────
// Reading the selected row
// ─────────────────────────────────────────────────────────────────────────────
function toE164(raw) {
  var d = String(raw == null ? '' : raw).replace(/\D/g, '');
  if (d.indexOf('0011') === 0) d = d.substring(4);
  if (d.indexOf('61') === 0 && d.length >= 11) d = '0' + d.substring(2);
  if (d.length === 9 && d.charAt(0) === '4') d = '0' + d;
  if (d.length !== 10 || d.charAt(0) !== '0') return null;
  return '+61' + d.substring(1);
}

function prettyPhone(e164) {
  if (!e164) return '';
  var n = '0' + e164.substring(3);
  return n.charAt(1) === '4'
    ? n.substring(0, 4) + ' ' + n.substring(4, 7) + ' ' + n.substring(7)
    : '(' + n.substring(0, 2) + ') ' + n.substring(2, 6) + ' ' + n.substring(6);
}

function dialerUrl(e164, callId) {
  return 'https://app.justcall.io/dialer'
    + '?numbers=' + encodeURIComponent(e164)
    + '&medium=custom'
    + '&metadata=' + encodeURIComponent(callId || '')
    + '&metadata_type=string';
}

/**
 * The sidebar polls this. Returns everything needed to render, including the
 * refusals — the client never decides whether a call is allowed.
 */
function getSelectedRow() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getActiveSheet();
  if (sheet.getName() !== TAB) {
    return { state: 'wrong_tab', tab: sheet.getName(), want: TAB };
  }
  assertLayout(sheet);

  var row = sheet.getActiveRange().getRow();
  if (row < 2) return { state: 'no_row' };

  var vals = sheet.getRange(row, 1, 1, C.callId).getValues()[0];
  var get = function (i) { return String(vals[i - 1] == null ? '' : vals[i - 1]).trim(); };

  var callId = get(C.callId);
  // A row with no Call ID is a day-separator, exactly as is_separator() defines
  // it in sheet_common.py. Same rule, so the two never disagree.
  if (!callId) return { state: 'separator', label: get(1) };

  var e164 = toE164(get(C.phone));
  var dnc = get(C.dncWashed);
  var occupant = get(C.occupant);

  var blocks = [];
  // Positive test, never a negative one: the row is dialable only if the wash
  // column holds a real date. "NOT WASHED", blank, and anything unrecognised
  // all fail, which is the safe direction (DNCR s11(6) puts the burden on us).
  if (!dnc || dnc.indexOf('NOT WASHED') !== -1 || dnc.indexOf('⛔') !== -1) {
    blocks.push('No current DNC wash on this row (column J reads "' +
                (dnc || 'empty') + '"). DNCR Act 2006 s11(3) gives the defence ' +
                'only for 30 days after our own submission.');
  }
  if (!e164) {
    blocks.push('Column D does not hold a dialable Australian number ("' +
                get(C.phone) + '").');
  }

  var gate = timeGate();
  if (!gate.ok) blocks.push(gate.reason);

  var warnings = [];
  if (occupant.indexOf('PRIOR OCCUPANT') !== -1) {
    warnings.push('Occupancy check says PRIOR OCCUPANT — this person may have ' +
                  'sold years ago. Confirm who you are speaking to before the hook.');
  } else if (occupant.indexOf('unconfirmed') !== -1 || occupant === 'not assessed') {
    warnings.push('Occupancy is ' + (occupant || 'not assessed') +
                  ' — do not assume they still own the property.');
  }

  return {
    state: 'ok',
    row: row,
    callId: callId,
    name: get(C.name),
    phone: prettyPhone(e164),
    e164: e164,
    address: get(C.address),
    suburb: get(C.suburb),
    whyNow: get(C.whyNow),
    track: get(C.track),
    property: get(C.property),
    dnc: dnc,
    occupant: occupant,
    outcome: get(C.outcome),
    comments: get(C.comments),
    blocks: blocks,
    warnings: warnings,
    needsHolidayConfirm: !!gate.needsHolidayConfirm,
    holidayNote: gate.holidayNote || '',
    clock: gate.clock || '',
    closesAt: gate.closesAt || '',
    url: (blocks.length === 0) ? dialerUrl(e164, callId) : '',
    desktopUrl: (blocks.length === 0) ? 'justcall://' + e164 : ''
  };
}


// ─────────────────────────────────────────────────────────────────────────────
// Writing back
// ─────────────────────────────────────────────────────────────────────────────
/**
 * Stamp the outcome for a row, located by Call ID — never by row number.
 *
 * Row numbers move every single day (call_list_to_sheet.py inserts each new day
 * at the top and pushes everything down), so a write addressed by position would
 * land on a different person's row than the one the panel was showing.
 *
 * Columns L/M/N are human-owned: scripts/sheet_common.py has a hard guard
 * (assert_machine_range) stopping the Python side from ever touching them. This
 * write is a different thing — it is YOU pressing a button, with a bigger target
 * than the cell — but it still honours the intent of that guard:
 *   - the outcome is only overwritten when `force` is set, after you confirm;
 *   - comments are APPENDED with a timestamp, never replaced.
 * Nothing you typed can be lost by pressing a button here.
 */
function logOutcome(callId, outcome, comment, force) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TAB);
  if (!sheet) throw new Error('Tab "' + TAB + '" not found.');
  assertLayout(sheet);

  var last = sheet.getLastRow();
  if (last < 2) throw new Error('Sheet has no data rows.');

  var ids = sheet.getRange(2, C.callId, last - 1, 1).getValues();
  var row = -1;
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]).trim() === String(callId).trim()) { row = i + 2; break; }
  }
  if (row === -1) {
    throw new Error('Call ID ' + callId + ' is no longer in the sheet. Nothing ' +
                    'was written. Re-select the row and try again.');
  }

  var existing = String(sheet.getRange(row, C.outcome).getValue() || '').trim();
  if (outcome) {
    if (existing && existing !== outcome && !force) {
      return { status: 'conflict', existing: existing, row: row };
    }
    sheet.getRange(row, C.outcome).setValue(outcome);
  }

  if (comment) {
    var stamp = Utilities.formatDate(new Date(), TZ, 'd MMM h:mm a');
    var prior = String(sheet.getRange(row, C.comments).getValue() || '').trim();
    var line = '[' + stamp + '] ' + comment;
    sheet.getRange(row, C.comments).setValue(prior ? prior + '\n' + line : line);
  }

  SpreadsheetApp.flush();
  return { status: 'ok', row: row };
}
