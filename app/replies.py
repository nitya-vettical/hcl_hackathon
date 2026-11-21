"""Deterministic reply templates. Used in mock mode and whenever an LLM draft fails the critic,
so every number shown is copied straight from tool output."""

SLOT_PROMPTS = {
    "en": {"from": "which station you're starting from", "to": "where you're going",
           "date": "your travel date", "class": "which class (SL, 3A, 2A, 1A or CC)",
           "train_no": "the 5-digit train number"},
    "hinglish": {"from": "aap kis station se chalenge", "to": "aapko kahan jaana hai",
                 "date": "yatra ki tareekh", "class": "kaunsi class (SL, 3A, 2A, 1A ya CC)",
                 "train_no": "5 ankon ka train number"},
}


def _l(lang: str) -> str:
    return "hinglish" if lang in ("hinglish", "hi") else "en"


def rs(x) -> str:
    x = float(x)
    return f"Rs {x:,.0f}" if x == int(x) else f"Rs {x:,.2f}"


def clarify(missing: list[str], problems: list[dict], lang: str) -> str:
    l = _l(lang)
    parts = []
    for p in problems:
        if "ambiguous" in p:
            opts = " or ".join(f"{o['name']} ({o['code']})" for o in p["ambiguous"])
            parts.append(f"for '{p['text']}', did you mean {opts}" if l == "en"
                         else f"'{p['text']}' se aapka matlab {opts.replace(' or ', ' ya ')} hai")
        elif p.get("suggestions"):  # a likely typo of a real station
            opts = " or ".join(f"{o['name']} ({o['code']})" for o in p["suggestions"])
            parts.append(f"for '{p['text']}', did you mean {opts}" if l == "en"
                         else f"'{p['text']}' se aapka matlab {opts.replace(' or ', ' ya ')} hai")
        else:
            parts.append(f"I couldn't recognise '{p['text']}', please check it" if l == "en"
                         else f"'{p['text']}' samajh nahi aaya, kripya dobara batayein")
    asks = [SLOT_PROMPTS[l][m] for m in missing if m in SLOT_PROMPTS[l]]
    if asks:
        joined = asks[0] if len(asks) == 1 else ", ".join(asks[:-1]) + (" and " if l == "en" else " aur ") + asks[-1]
        parts.append(("Could you tell me " if l == "en" else "Kripya batayein: ") + joined)
    return " ".join(p[0].upper() + p[1:] + "?" for p in parts)


def gave_up(missing: list[str], lang: str) -> str:
    asks = ", ".join(SLOT_PROMPTS[_l(lang)].get(m, m) for m in missing)
    if _l(lang) == "en":
        return (f"I still need {asks} to help with this. Please send it all in one message, "
                f"for example: 'Trains from Pune to Nagpur on 5 Dec in 3A'.")
    return f"Iske liye mujhe {asks} chahiye. Kripya sab ek hi message mein bhejein."


def which_booking(bookings: list[dict], lang: str) -> str:
    opts = ", ".join(f"{b['booking_id']} ({b['train_no']} on {b['journey_date']})" for b in bookings)
    return (f"Which booking do you mean: {opts}?" if _l(lang) == "en"
            else f"Aap kaunsi booking ki baat kar rahe hain: {opts}?")


def train_search(out: dict, extras: dict) -> str:
    if not out["trains"]:
        win = out.get("time_window") or {}
        w = "".join(f" {k} {v}" for k, v in win.items())
        return f"No Ujjwal Rail trains found from {out['from']} to {out['to']} on {out['date']}{w}."
    lines = []
    for t in out["trains"]:
        s = f"{t['train_no']} {t['name']}: departs {t['departs']}, arrives {t['arrives']}"
        if t["departs_after_midnight"]:
            s += " (leaves just after midnight)"
        if t["train_no"] in extras:
            s += f"; {extras[t['train_no']]}"
        lines.append(s)
    return f"Trains from {out['from']} to {out['to']} on {out['date']}:\n- " + "\n- ".join(lines)


def seats_line(s: dict) -> str:
    st = s["status"]
    if st == "AVAILABLE":
        return f"{s['class']}: {s['available']} seats available"
    if st == "RAC":
        return f"{s['class']}: no confirmed seats, RAC {s['rac']}"
    if st == "WAITLIST":
        return f"{s['class']}: waitlist {s['waitlist']}"
    return {"NOT_RUNNING": f"the train does not run on {s.get('journey_date')}",
            "CLASS_NOT_ON_TRAIN": f"{s['class']} is not available on this train",
            "NO_SUCH_TRAIN": f"there is no train {s['train_no']}",
            "NO_DATA": f"no seat data for {s.get('journey_date')}"}[st]


def fare_line(f: dict) -> str:
    if not f.get("found"):
        return f"no fare found for {f['class']} from {f['from']} to {f['to']}"
    return f"{f['class']} fare from {f['from']} to {f['to']}: {rs(f['fare'])}"


def seat_fare(seats: dict | None, fare: dict | None, needs_date: bool) -> str:
    parts = []
    if seats:
        parts.append(f"Train {seats['train_no']} on {seats['travel_date']}: {seats_line(seats)}.")
    if fare:
        parts.append(fare_line(fare)[0].upper() + fare_line(fare)[1:] + ".")
    if needs_date:
        parts.append("Tell me your travel date to check seats.")
    return " ".join(parts)


def booking_status(out: dict) -> str:
    if not out["bookings"]:
        return "I couldn't find a matching upcoming booking on your account."
    lines = []
    for b in out["bookings"]:
        trav = "; ".join(
            f"{t['traveller_name']}: {t['status']}" + (f" {t['coach']}/{t['berth']}" if t.get("coach") else "")
            for t in b["travellers"])
        lines.append(f"{b['booking_id']}: train {b['train_no']}, {b['from']} to {b['to']}, departs "
                     f"{b['departs']}, {b['class']}, status {b['status']}" + (f" ({trav})" if trav else ""))
    return "\n".join(lines)


def refund(q: dict) -> str:
    if q.get("error"):
        return "I can't work out this refund right now because a rule value is missing. Please try again later."
    bid = q["booking_id"]
    if q.get("reason") == "already_cancelled":
        return f"Booking {bid} is already cancelled."
    if q.get("reason") == "train_cancelled_by_operator":
        return f"Train for booking {bid} was cancelled by Ujjwal Rail, so the refund is {rs(q['refund'])}."
    if q.get("reason") == "already_departed":
        return f"Booking {bid} can no longer be cancelled: the train has already departed."
    src = ", ".join(dict.fromkeys(s.split("#")[0] for s in q.get("rule_sources", [])))
    return (f"If you cancel booking {bid} now ({q['hours_before_departure']} hours before departure), "
            f"the charge is {rs(q['charge'])} and you get back {rs(q['refund'])} of the {rs(q['amount_paid'])} "
            f"paid" + (f" (as per {src})." if src else "."))


# ---------- safe changes ----------

REFUSAL_REASONS = {
    "not_found": "I can only act on bookings made from your own account.",
    "already_cancelled": "That booking is already cancelled.",
    "already_departed": "The train has already departed, so this can't be changed.",
    "train_cancelled_by_operator": "This train was cancelled by Ujjwal Rail, so the booking can't be cancelled again; "
                                   "the refund for operator cancellations is automatic.",
    "past_boarding_change_cutoff": "The boarding station can no longer be changed: the cut-off before departure has passed.",
    "station_not_on_route_before_destination": "That station is not a stop on this train before your destination.",
    "same_station": "You're already boarding at that station.",
    "no_such_train": "There is no such train.",
    "class_not_on_train": "That class is not available on this train.",
    "not_running": "The train does not run on that date.",
    "no_data": "Booking is not open for that date yet.",
    "no_fare_for_segment": "I couldn't find a fare for that journey, so I can't book it.",
    "rule_value_missing": "I can't do this right now because a rule value is missing. Please try again later.",
}


def change_refused(reason: str, extra: dict | None = None) -> str:
    text = REFUSAL_REASONS.get(reason, "Sorry, that change isn't allowed.")
    if reason.startswith("booking_"):
        text = f"This booking is {reason.split('_', 1)[1].replace('_', ' ')}, so it can't be changed."
    if extra and reason == "past_boarding_change_cutoff":
        text += (f" Changes are allowed only more than {extra['cutoff_hours']:g} hours before departure "
                 f"(as per {extra['rule_source'].split('#')[0]}).")
    return text


def _ttl(pa: dict) -> str:
    return f"Nothing has changed yet. Press Confirm within {pa['ttl_minutes']} minutes to go ahead, or Cancel to drop it."


def preview(action_type: str, p: dict, pa: dict) -> str:
    if action_type == "cancel_booking":
        src = ", ".join(dict.fromkeys(s.split("#")[0] for s in p.get("rule_sources", [])))
        return (f"Cancelling booking {p['booking_id']} ({p['train_no']}, {p['from']} to {p['to']}, departs "
                f"{p['departs']}, {p['class']}, {p['travellers']} traveller(s)) now gives you a refund of "
                f"{rs(p['refund'])} (charge {rs(p['charge'])} on {rs(p['amount_paid'])} paid"
                + (f", as per {src}" if src else "") + "). " + _ttl(pa))
    if action_type == "change_boarding":
        return (f"Changing the boarding station of booking {p['booking_id']} (train {p['train_no']}) from "
                f"{p['old_boarding']} to {p['new_boarding']} ({p['new_boarding_name']}). You would board at "
                f"{p['new_departs']}. The fare does not change. " + _ttl(pa))
    status = {"CONFIRMED": "confirmed berths", "RAC": "RAC", "WAITLISTED": "waitlisted"}[p["expected_status"]]
    return (f"Booking {p['passengers']} {p['class']} ticket(s) on train {p['train_no']} from {p['from']} to {p['to']}, "
            f"departing {p['departs']}: {rs(p['fare_per_person'])} per person, total {rs(p['total'])} "
            f"(pretend payment), expected status: {status}. " + _ttl(pa))


def done(action_type: str, r: dict) -> str:
    ok = r.get("verification", {}).get("verified")
    check = " I've checked the booking and the change is in place." if ok else \
        " Warning: I could not verify the change; a staff member will check it."
    if action_type == "cancel_booking":
        return f"Done. Booking {r['booking_id']} is cancelled and {rs(r['refund'])} will be refunded." + check
    if action_type == "change_boarding":
        return f"Done. Booking {r['booking_id']} now boards at {r['from']}, departing {r['departs']}." + check
    return (f"Done. Your booking {r['booking_id']} is {r['status']} for {r['passengers']} traveller(s), "
            f"total {rs(r['amount_paid'])}." + check)


def action_dropped(action_id: str) -> str:
    return f"Okay, I've dropped the proposed change {action_id}. Nothing was changed."


def use_confirm_button(pa: dict) -> str:
    return (f"To go ahead, press Confirm for {pa['action_id']}. For your safety I can't confirm changes from a "
            f"chat message.")


def not_served(places: list[str], cities: list[str], lang: str) -> str:
    names = " and ".join(f"'{p}'" for p in places)
    served = ", ".join(cities)
    if _l(lang) == "en":
        return (f"Ujjwal Rail doesn't have a station at {names}, so I can't help with that journey. "
                f"We serve: {served}.")
    return (f"Ujjwal Rail ka {names.replace(' and ', ' aur ')} mein koi station nahi hai, isliye is yatra mein "
            f"madad nahi kar sakta. Hamare stations: {served}.")
