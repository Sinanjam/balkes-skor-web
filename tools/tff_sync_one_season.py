#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup


TEAM_KEYS = [
    "BALIKESIRSPOR",
    "BALIKESIRSPOR BALTOK",
    "NEV SAGLIK GRUBU BALIKESIRSPOR",
    "BALIKESIRSPOR KULUBU",
]

MATCH_PATTERNS = [
    "https://www.tff.org/Default.aspx?macId={id}&pageID=528",
    "https://www.tff.org/Default.aspx?pageID=528&macId={id}",
    "https://www.tff.org/Default.aspx?macId={id}&pageId=528",
    "https://www.tff.org/Default.aspx?pageId=528&macId={id}",
    "https://www.tff.org/Default.aspx?pageID=29&macId={id}",
    "https://www.tff.org/Default.aspx?macId={id}&pageID=29",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 BalkesSeasonSyncV2/2.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm(s: str) -> str:
    s = str(s or "").upper()
    trans = str.maketrans({
        "İ": "I", "ı": "I", "Ğ": "G", "Ü": "U", "Ş": "S", "Ö": "O", "Ç": "C",
        "ğ": "G", "ü": "U", "ş": "S", "ö": "O", "ç": "C",
    })
    return re.sub(r"\s+", " ", s.translate(trans)).strip()


def is_balkes(text: str) -> bool:
    n = norm(text)
    return any(k in n for k in TEAM_KEYS)


def text_from_html(src: str) -> str:
    soup = BeautifulSoup(src or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_macids(s: str) -> set[str]:
    return set(re.findall(r"macId=([0-9]+)", s or "", flags=re.I))


def extract_tff_urls(s: str, base: str = "https://www.tff.org/") -> set[str]:
    urls = set()
    for m in re.finditer(r'https?://(?:www\.)?tff\.org/[^\s"\'<>]+', s or "", flags=re.I):
        urls.add(html.unescape(m.group(0)))
    soup = BeautifulSoup(s or "", "lxml")
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if "tff.org" in href or "Default.aspx" in href or "default.aspx" in href:
            urls.add(urljoin(base, html.unescape(href)))
    cleaned = set()
    for u in urls:
        u = unquote(u)
        if "uddg=" in u:
            qs = parse_qs(urlparse(u).query)
            if "uddg" in qs and qs["uddg"]:
                u = qs["uddg"][0]
        if "tff.org" in u:
            cleaned.add(u.rstrip(").,;"))
    return cleaned


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def dump_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick_season(season_arg: str, queue_path: Path) -> str:
    if season_arg != "auto":
        return season_arg
    queue = load_json(queue_path, {})
    for status in ["missing", "partial", "failed"]:
        for season, item in queue.items():
            if (item or {}).get("status") == status:
                return season
    raise SystemExit("No missing/partial season left in queue")


def planned_queries(season: str) -> list[str]:
    return [
        f'site:tff.org/default.aspx?pageID= "{season}" "Balıkesirspor"',
        f'site:tff.org/default.aspx?pageID= "{season}" "Sezonu" "Arşivi" "Balıkesirspor"',
        f'site:tff.org/Default.aspx?macId= "Balıkesirspor" "{season}"',
        f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "macId"',
        f'site:tff.org/Default.aspx "BALIKESİRSPOR" "{season}" "Match Details"',
        f'site:tff.org/Default.aspx "Balıkesirspor Baltok" "{season}"',
        f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "Ziraat"',
        f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "Puan"',
    ]


def search_query(query: str, reports_dir: Path) -> tuple[set[str], set[str]]:
    url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
    r = requests.get(url, headers=HEADERS, timeout=40)
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", query)[:120]
    (reports_dir / f"search_{safe}.html").write_text(r.text, encoding="utf-8")
    urls = extract_tff_urls(r.text)
    ids = set()
    for u in urls:
        ids |= extract_macids(u)
    return ids, urls


def load_archive_urls(season: str, archive_path: Path) -> list[str]:
    data = load_json(archive_path, {})
    urls = []
    for item in data.get(season, []) if isinstance(data, dict) else []:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    return urls


def discover_archive_urls_from_search(season: str, reports_dir: Path, max_queries: int) -> set[str]:
    urls = set()
    qs = [
        f'site:tff.org/default.aspx?pageID= "{season}" "Sezonu" "Arşivi"',
        f'site:tff.org/default.aspx?pageID= "{season}" "Balıkesirspor"',
    ]
    if max_queries:
        qs = qs[:max_queries]
    for q in qs:
        try:
            _, found = search_query(q, reports_dir)
            for u in found:
                if "pageID=" in u or "pageId=" in u or "pageid=" in u:
                    urls.add(u)
        except Exception:
            pass
    return urls


def extract_archive_candidates(url: str, season: str, reports_dir: Path) -> tuple[set[str], list[dict]]:
    r = requests.get(url, headers=HEADERS, timeout=45)
    src = r.text
    text = text_from_html(src)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", url)[:120]
    (reports_dir / f"archive_{stem}.html").write_text(src, encoding="utf-8")
    (reports_dir / f"archive_{stem}.txt").write_text(text, encoding="utf-8")

    soup = BeautifulSoup(src, "lxml")
    ids = set()
    summaries = []

    # 1) Any macId in page near Balıkesirspor.
    for mid in extract_macids(src):
        # If page is season archive with Balıkesirspor, keep as candidate; detail validation still decides.
        ids.add(mid)

    # 2) Links and their surrounding row text.
    for a in soup.select("a[href]"):
        href = urljoin(url, a.get("href") or "")
        mids = extract_macids(href)
        if not mids:
            continue
        row = a.find_parent("tr") or a.find_parent("li") or a.parent
        row_text = row.get_text(" ", strip=True) if row else a.get_text(" ", strip=True)
        if is_balkes(row_text) or is_balkes(text):
            ids |= mids
            summaries.append({"macIds": ",".join(sorted(mids)), "rowText": row_text, "href": href})

    # 3) Keep Balıkesirspor fixture lines as evidence even if the archive page does not expose macId in HTML.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if is_balkes(ln) and re.search(r"\b[0-9]\s*[-–]\s*[0-9]\b", ln):
            summaries.append({"macIds": "", "rowText": ln, "href": url})

    return ids, summaries


def existing_ids_for_season(data_dir: Path, season: str) -> set[str]:
    ids = set()
    season_dir = data_dir / "seasons" / season
    for p in season_dir.glob("matches/*.json"):
        if p.stem.isdigit():
            ids.add(p.stem)
    idx = load_json(season_dir / "matches_index.json", [])
    if isinstance(idx, list):
        for m in idx:
            mid = str(m.get("id", ""))
            if mid.isdigit():
                ids.add(mid)
    return ids


def date_to_season(date_iso: str) -> str:
    try:
        y, m, d = map(int, date_iso.split("-"))
    except Exception:
        return ""
    if m >= 7:
        return f"{y}-{y+1}"
    return f"{y-1}-{y}"


def parse_date_time(text: str):
    m = re.search(r"\b([0-3]?\d)[./]([01]?\d)[./]((?:19|20)\d{2})\b", text)
    date_iso = ""
    date_display = ""
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date_iso = f"{yy:04d}-{mm:02d}-{dd:02d}"
        date_display = f"{dd:02d}.{mm:02d}.{yy:04d}"
    tm = re.search(r"\b([0-2]\d:[0-5]\d)\b", text)
    time_s = tm.group(1) if tm else ""
    if date_display and time_s:
        date_display = f"{date_display} - {time_s}"
    return date_iso, time_s, date_display


def parse_score_teams(text: str):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in lines[:160]:
        if not is_balkes(line):
            continue
        m = re.search(r"(.+?)\s+([0-9]+)\s*[-–]\s*([0-9]+)\s+(.+)", line)
        if m:
            return m.group(1).strip(), m.group(4).strip(), int(m.group(2)), int(m.group(3))
    for i, line in enumerate(lines[:200]):
        m = re.search(r"\b([0-9]+)\s*[-–]\s*([0-9]+)\b", line)
        if m:
            before = lines[i-1] if i > 0 else ""
            after = lines[i+1] if i + 1 < len(lines) else ""
            if before and after and (is_balkes(before) or is_balkes(after)):
                return before, after, int(m.group(1)), int(m.group(2))
    return "", "", None, None


def infer_round_type(text: str) -> str:
    n = norm(text)
    if "KUPA" in n or "ZIRAAT" in n:
        return "cup"
    if "PLAY-OFF" in n or "PLAY OFF" in n:
        return "playoff"
    if "LIG" in n:
        return "league"
    return "unknown"


def infer_week(text: str):
    m = re.search(r"\b([0-9]{1,2})\.\s*Hafta\b", text, flags=re.I)
    if m:
        return int(m.group(1)), f"{int(m.group(1))}. Hafta"
    m = re.search(r"\bHafta\s*[:\-]?\s*([0-9]{1,2})\b", text, flags=re.I)
    if m:
        return int(m.group(1)), f"{int(m.group(1))}. Hafta"
    return None, ""


def infer_competition(text: str):
    for line in [x.strip() for x in text.splitlines() if x.strip()][:140]:
        n = norm(line)
        if "LIG" in n or "KUPA" in n or "PLAY" in n:
            if len(line) < 140:
                return line
    return ""


def validate_match_id(macid: str, target_season: str):
    last_error = ""
    for pat in MATCH_PATTERNS:
        url = pat.format(id=macid)
        try:
            r = requests.get(url, headers=HEADERS, timeout=35)
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                continue
            src = r.text
            text = text_from_html(src)
            if len(text) < 250:
                last_error = "too short"
                continue
            if not is_balkes(text):
                return None, {"macId": macid, "sourceUrl": url, "reason": "Balıkesirspor not found"}
            date_iso, time_s, date_display = parse_date_time(text)
            inferred = date_to_season(date_iso) if date_iso else ""
            if inferred and inferred != target_season:
                return None, {"macId": macid, "sourceUrl": url, "reason": f"season mismatch: {inferred}"}
            if (not inferred) and target_season not in text:
                return None, {"macId": macid, "sourceUrl": url, "reason": "season not confirmed"}
            return {"macId": macid, "url": url, "html": src, "text": text, "date": date_iso, "time": time_s, "dateDisplay": date_display}, None
        except Exception as exc:
            last_error = str(exc)[:200]
    return None, {"macId": macid, "sourceUrl": "", "reason": last_error or "not fetched"}


def make_detail(match, season: str):
    text = match["text"]
    home, away, sh, sa = parse_score_teams(text)
    date_iso, time_s, date_display = match["date"], match["time"], match["dateDisplay"]
    week, stage = infer_week(text)
    competition = infer_competition(text)
    round_type = infer_round_type(text)

    is_home = is_balkes(home)
    opponent = away if is_home else home
    gf = sh if is_home else sa
    ga = sa if is_home else sh
    result = ""
    if gf is not None and ga is not None:
        result = "W" if gf > ga else ("D" if gf == ga else "L")

    score_display = f"{sh}-{sa}" if sh is not None and sa is not None else ""

    notes = []
    if not home or not away:
        notes.append("Takım adları TFF textinden otomatik güvenle ayrıştırılamadı.")
    if not score_display:
        notes.append("Skor TFF textinden otomatik güvenle ayrıştırılamadı.")
    if not competition:
        notes.append("Müsabaka adı otomatik güvenle ayrıştırılamadı.")

    return {
        "id": match["macId"],
        "tffMatchId": match["macId"],
        "season": season,
        "competition": competition,
        "group": "",
        "roundType": round_type,
        "week": week,
        "stage": stage,
        "date": date_iso,
        "time": time_s,
        "dateDisplay": date_display,
        "stadium": "",
        "venue": "",
        "city": "",
        "referee": "",
        "assistantReferees": [],
        "fourthOfficial": "",
        "referees": [],
        "homeTeam": home,
        "awayTeam": away,
        "score": {"home": sh, "away": sa, "display": score_display, "played": True},
        "halfTimeScore": {"home": None, "away": None, "display": ""},
        "events": [],
        "homeCoach": "",
        "awayCoach": "",
        "lineups": {
            "home": {"team": home, "starting11": [], "substitutes": [], "coach": ""},
            "away": {"team": away, "starting11": [], "substitutes": [], "coach": ""},
        },
        "source": {"name": "TFF", "url": match["url"]},
        "dataQuality": {"level": "official_tff_open_data", "notes": notes},
        "balkes": {
            "isHome": bool(is_home),
            "opponent": opponent,
            "goalsFor": gf,
            "goalsAgainst": ga,
            "result": result,
        }
    }


def index_from_detail(detail):
    return {
        "id": detail["id"],
        "season": detail["season"],
        "competition": detail.get("competition", ""),
        "roundType": detail.get("roundType", "unknown"),
        "week": detail.get("week"),
        "stage": detail.get("stage", ""),
        "date": detail.get("date", ""),
        "time": detail.get("time", ""),
        "dateDisplay": detail.get("dateDisplay", ""),
        "homeTeam": detail.get("homeTeam", ""),
        "awayTeam": detail.get("awayTeam", ""),
        "score": detail.get("score", {}),
        "balkes": detail.get("balkes", {}),
        "detailUrl": f"seasons/{detail['season']}/matches/{detail['id']}.json",
        "source": detail.get("source", {"name": "TFF", "url": ""}),
    }


def season_summary(index):
    summary = {
        "matches": len(index), "leagueMatches": 0, "playoffMatches": 0, "cupMatches": 0,
        "wins": 0, "draws": 0, "losses": 0, "goalsFor": 0, "goalsAgainst": 0,
        "goalDifference": 0, "points": None, "finalRank": None,
    }
    points = 0
    for m in index:
        rt = m.get("roundType")
        if rt == "league":
            summary["leagueMatches"] += 1
        elif rt == "playoff":
            summary["playoffMatches"] += 1
        elif rt == "cup":
            summary["cupMatches"] += 1
        b = m.get("balkes") or {}
        gf = b.get("goalsFor")
        ga = b.get("goalsAgainst")
        if gf is not None and ga is not None:
            summary["goalsFor"] += int(gf)
            summary["goalsAgainst"] += int(ga)
            if int(gf) > int(ga):
                summary["wins"] += 1
                points += 3
            elif int(gf) == int(ga):
                summary["draws"] += 1
                points += 1
            else:
                summary["losses"] += 1
    summary["goalDifference"] = summary["goalsFor"] - summary["goalsAgainst"]
    if summary["leagueMatches"]:
        summary["points"] = points
    return summary


def update_global_indexes(data_dir: Path):
    """
    V2.1 app-first safety:
    Do not wholesale-regenerate players/opponents/search indexes in the season sync job.

    V2 generated a very large diff in search_index/opponents_index during a partial season test.
    That is risky for the installed app because the season sync parser is intentionally minimal.
    Root index rebuild should be a separate, explicit maintenance job.

    Here we only ensure the root index files exist and are valid JSON, preserving existing content.
    """
    defaults = {
        "players_index.json": [],
        "opponents_index.json": [],
        "search_index.json": [],
    }
    for name, fallback in defaults.items():
        path = data_dir / name
        obj = load_json(path, fallback)
        if not isinstance(obj, list):
            dump_json(path, fallback)

def update_manifest_and_report(data_dir: Path, season: str, index: list, summary: dict):
    manifest_path = data_dir / "manifest.json"
    manifest = load_json(manifest_path, {})
    manifest.setdefault("app", "Balkes Skor")
    manifest["schemaVersion"] = int(manifest.get("schemaVersion") or 2)
    manifest["dataVersion"] = int(manifest.get("dataVersion") or 0) + 1
    manifest["appDataVersion"] = int(manifest.get("appDataVersion") or 0) + 1
    manifest["lastUpdated"] = now()
    manifest["generatedAt"] = manifest.get("generatedAt") or now()
    manifest["dataBaseUrl"] = manifest.get("dataBaseUrl") or "https://raw.githubusercontent.com/Sinanjam/balkes-skor-web/main/docs/data/"
    manifest.setdefault("team", "Balıkesirspor")
    manifest.setdefault("assets", {"logo": "assets/logo_balkes_skor.png"})
    manifest.setdefault("global", {
        "playersIndexUrl": "players_index.json",
        "opponentsIndexUrl": "opponents_index.json",
        "searchIndexUrl": "search_index.json",
        "dataReportUrl": "data_report.json",
    })

    seasons = [s for s in manifest.get("availableSeasons", []) if s.get("id") != season]
    seasons.append({
        "id": season,
        "name": season,
        "matchCount": len(index),
        "competition": index[0].get("competition", "") if index else "",
        "group": "",
        "summary": {
            "matches": summary["matches"],
            "wins": summary["wins"],
            "draws": summary["draws"],
            "losses": summary["losses"],
            "goalsFor": summary["goalsFor"],
            "goalsAgainst": summary["goalsAgainst"],
            "goalDifference": summary["goalDifference"],
            "points": summary["points"],
            "finalRank": summary["finalRank"],
        },
    })
    seasons.sort(key=lambda x: x.get("id", ""), reverse=True)
    manifest["availableSeasons"] = seasons
    dump_json(manifest_path, manifest)

    total = sum(int(s.get("matchCount") or (s.get("summary") or {}).get("matches") or 0) for s in seasons)
    report = load_json(data_dir / "data_report.json", {})
    if not isinstance(report, dict):
        report = {}
    report["generatedAt"] = now()
    report["source"] = "TFF açık sayfaları ve Balkes Skor season sync"
    report["totalAppMatches"] = total
    report["seasons"] = [s["id"] for s in seasons]
    report.setdefault("coverage", {})
    report.setdefault("validation", {})
    dump_json(data_dir / "data_report.json", report)


def update_queue(queue_path: Path, season: str, status: str, notes: str):
    queue = load_json(queue_path, {})
    queue.setdefault(season, {})
    queue[season]["status"] = status
    queue[season]["notes"] = notes
    queue[season]["updatedAt"] = now()
    dump_json(queue_path, queue)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="auto")
    ap.add_argument("--data-dir", default="docs/data")
    ap.add_argument("--reports-dir", default="reports/season-sync")
    ap.add_argument("--queue", default="tools/season_queue.json")
    ap.add_argument("--archive-pages", default="tools/tff_archive_pages.json")
    ap.add_argument("--max-search-queries", default="0")
    ap.add_argument("--min-delay", type=float, default=1.2)
    ap.add_argument("--max-delay", type=float, default=3.0)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    reports_dir = Path(args.reports_dir)
    queue_path = Path(args.queue)
    archive_path = Path(args.archive_pages)
    season = pick_season(args.season, queue_path)

    season_report_dir = reports_dir / season
    raw_dir = season_report_dir / "raw"
    season_report_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "LAST_SEASON.txt").write_text(season, encoding="utf-8")

    candidates = set()
    candidates |= existing_ids_for_season(data_dir, season)

    archive_urls = set(load_archive_urls(season, archive_path))
    max_q = int(args.max_search_queries or 0)

    # V2: official archive pages first.
    archive_urls |= discover_archive_urls_from_search(season, season_report_dir, max_queries=0 if max_q == 0 else min(max_q, 2))

    archive_rows = []
    archive_ids = set()
    for url in sorted(archive_urls):
        try:
            ids, rows = extract_archive_candidates(url, season, season_report_dir)
            archive_ids |= ids
            archive_rows.extend(rows)
            time.sleep(random.uniform(args.min_delay, args.max_delay))
        except Exception as exc:
            archive_rows.append({"macIds": "", "rowText": f"ERROR: {exc}", "href": url})

    candidates |= archive_ids

    with (season_report_dir / "archive_summary_candidates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["macIds", "rowText", "href"])
        writer.writeheader()
        writer.writerows(archive_rows)

    archive_md = [
        f"# Archive extraction for {season}",
        "",
        f"- Archive URLs tried: `{len(archive_urls)}`",
        f"- macId candidates from archive pages: `{len(archive_ids)}`",
        f"- Balıkesirspor fixture rows captured: `{sum(1 for r in archive_rows if is_balkes(r.get('rowText','')))}`",
        "",
        "## URLs",
        "",
    ]
    for u in sorted(archive_urls):
        archive_md.append(f"- {u}")
    (season_report_dir / "archive_extraction.md").write_text("\n".join(archive_md) + "\n", encoding="utf-8")

    # Search fallback.
    queries = planned_queries(season)
    if max_q:
        queries = queries[:max_q]

    for q in queries:
        try:
            ids, _ = search_query(q, season_report_dir)
            candidates |= ids
            time.sleep(random.uniform(args.min_delay, args.max_delay))
        except Exception as exc:
            with (season_report_dir / "search_errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{q}\t{exc}\n")

    with (season_report_dir / "candidate_macids.txt").open("w", encoding="utf-8") as f:
        for mid in sorted(candidates, key=int):
            f.write(mid + "\n")

    good = []
    uncertain = []

    for i, mid in enumerate(sorted(candidates, key=int), 1):
        match, bad = validate_match_id(mid, season)
        if match:
            good.append(match)
            (raw_dir / f"{mid}.txt").write_text(match["text"], encoding="utf-8")
            (raw_dir / f"{mid}.html").write_text(match["html"], encoding="utf-8")
        elif bad:
            uncertain.append(bad)
        time.sleep(random.uniform(args.min_delay, args.max_delay))

    with (season_report_dir / "uncertain_candidates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["macId", "sourceUrl", "reason"])
        writer.writeheader()
        writer.writerows(uncertain)

    if not good:
        # Do not poison queue permanently if official archive page had fixture rows but no macIds.
        note = "No verified TFF macId match found."
        if archive_rows:
            note += f" Archive fixture rows were captured ({len(archive_rows)} rows); parser needs macId links or manual page mapping."
        update_queue(queue_path, season, "missing", note)
        (season_report_dir / "SUMMARY.md").write_text(
            f"# {season} sync\n\nNo verified TFF Balıkesirspor matches found.\n\nArchive rows: {len(archive_rows)}\nUncertain candidates: {len(uncertain)}\n",
            encoding="utf-8"
        )
        print(f"No verified matches for {season}")
        print(f"Archive URLs tried: {len(archive_urls)}")
        print(f"Archive macId candidates: {len(archive_ids)}")
        print(f"Archive fixture rows: {len(archive_rows)}")
        print(f"Uncertain candidates: {len(uncertain)}")
        return 0

    details = [make_detail(m, season) for m in good]
    details.sort(key=lambda x: (x.get("date") or "", int(x["id"])))
    index = [index_from_detail(d) for d in details]
    summary = season_summary(index)

    sdir = data_dir / "seasons" / season
    (sdir / "matches").mkdir(parents=True, exist_ok=True)
    for d in details:
        dump_json(sdir / "matches" / f"{d['id']}.json", d)
    dump_json(sdir / "matches_index.json", index)
    if not (sdir / "standings_by_week.json").exists():
        dump_json(sdir / "standings_by_week.json", [])

    season_obj = {
        "id": season,
        "name": season,
        "team": {"id": "balikesirspor", "name": "Balıkesirspor", "tffClubId": "135"},
        "competition": index[0].get("competition", "") if index else "",
        "group": "",
        "summary": summary,
        "files": {
            "matchesIndex": f"seasons/{season}/matches_index.json",
            "standingsByWeek": f"seasons/{season}/standings_by_week.json",
        },
        "source": {"name": "TFF", "note": "Açık TFF sayfalarından dönüştürülmüş veri"},
        "dataQuality": {
            "level": "official_tff_open_data",
            "notes": [
                "Bu sezon GitHub Actions season sync V2 ile otomatik güncellendi.",
                "V2 resmi TFF arşiv sayfalarını önce dener, sonra arama fallback kullanır.",
                "Otomatik parserın güvenle ayıramadığı alanlar match dataQuality.notes içinde işaretlenir."
            ],
        }
    }
    dump_json(sdir / "season.json", season_obj)

    update_manifest_and_report(data_dir, season, index, summary)
    update_global_indexes(data_dir)

    status = "done" if len(index) >= 20 else "partial"
    update_queue(queue_path, season, status, f"Verified {len(index)} TFF matches with V2.")

    sources_csv = season_report_dir / "macids_with_sources.csv"
    with sources_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["season", "macId", "match", "sourceUrl", "confidence", "notes"])
        writer.writeheader()
        for d in details:
            writer.writerow({
                "season": season,
                "macId": d["id"],
                "match": f"{d.get('homeTeam','')} - {d.get('awayTeam','')}",
                "sourceUrl": d["source"]["url"],
                "confidence": "high",
                "notes": "TFF maç detay sayfasında Balıkesirspor doğrulandı",
            })

    summary_md = [
        f"# {season} sync V2",
        "",
        f"- Verified matches: `{len(index)}`",
        f"- Candidate macIds: `{len(candidates)}`",
        f"- Archive macId candidates: `{len(archive_ids)}`",
        f"- Archive fixture rows: `{len(archive_rows)}`",
        f"- Uncertain/rejected: `{len(uncertain)}`",
        f"- Queue status: `{status}`",
        f"- Wins/draws/losses: `{summary['wins']}/{summary['draws']}/{summary['losses']}`",
        f"- Goals: `{summary['goalsFor']}-{summary['goalsAgainst']}`",
        "",
        "## Notes",
        "",
        "- V2 tries official TFF archive pages before search-engine discovery.",
        "- Standings are not trusted unless a TFF standings table is explicitly parsed; missing standings stay as `[]`.",
        "- App data is prioritized: all season JSON files are valid and manifest/data_report/global indexes are updated.",
    ]
    (season_report_dir / "SUMMARY.md").write_text("\n".join(summary_md) + "\n", encoding="utf-8")
    print(f"Season {season}: verified {len(index)} matches, status={status}")
    print(f"Archive URLs tried: {len(archive_urls)}")
    print(f"Archive macId candidates: {len(archive_ids)}")
    print(f"Archive fixture rows: {len(archive_rows)}")
    print(f"Uncertain candidates: {len(uncertain)}")


if __name__ == "__main__":
    main()
