#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# WayAI Web GUI — Wayback & Common Crawl Recon
# Powered by ynsmroztas (x.com/ynsmroztas) • powered by mitsec

import warnings, urllib3
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

from flask import Flask, render_template, request, redirect, url_for
import requests, os, re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

def waybackurls(domain, from_date=None, to_date=None):
    base_url = "https://web.archive.org/cdx/search/cdx"
    params = {"url": f"{domain}/*", "output": "json", "collapse": "urlkey"}
    if from_date: params["from"] = from_date
    if to_date: params["to"] = to_date
    try:
        r = requests.get(base_url, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()
        return [row[2] for row in rows[1:]]
    except Exception:
        return []

def commoncrawlurls(domain):
    try:
        indexes = requests.get("https://index.commoncrawl.org/collinfo.json", timeout=15).json()
    except Exception:
        return []
    urls = []
    for idx in indexes:
        api_url = f"{idx['cdx-api']}?url={domain}/*&output=json&fl=url&collapse=urlkey"
        try:
            r = requests.get(api_url, timeout=25)
            for line in r.iter_lines():
                if line:
                    s = line.decode(errors="ignore")
                    if s.startswith("http"):
                        urls.append(s)
        except Exception:
            continue
    return urls

def filter_urls(urls, exts=None, with_params=False):
    filtered = []
    for u in urls:
        if exts:
            if not any(u.lower().endswith(e) or (f"{e}?" in u.lower()) for e in exts):
                continue
        if with_params and "?" not in u:
            continue
        filtered.append(u)
    return filtered

def extract_subdomains(urls, root_domain):
    subs = set()
    rx = re.compile(rf"([a-z0-9_-]+\.)+{re.escape(root_domain)}", re.I)
    for u in urls:
        m = rx.search(u)
        if m:
            subs.add(m.group(0).lower())
    return sorted(subs)

def check_url(url):
    try:
        r = requests.head(url, timeout=6, allow_redirects=True)
        return url, r.status_code, r.headers.get("Content-Length", "-")
    except Exception:
        return url, "ERR", "-"

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    domain = request.form.get("domain","").strip()
    from_date = request.form.get("from_date","").strip() or None
    to_date = request.form.get("to_date","").strip() or None
    include_cc = request.form.get("include_cc") == "on"
    with_params = request.form.get("with_params") == "on"
    status = request.form.get("status") == "on"
    scan_subs = request.form.get("scan_subs") == "on"
    exts_text = request.form.get("exts","").strip()
    exts = [e.strip() for e in exts_text.split() if e.strip()] if exts_text else None
    threads = int(request.form.get("threads","20"))

    if not domain:
        return redirect(url_for("index"))

    urls = waybackurls(domain, from_date, to_date)
    if include_cc:
        urls += commoncrawlurls(domain)
    urls = list(OrderedDict.fromkeys(urls))
    if exts or with_params:
        urls = filter_urls(urls, exts=exts, with_params=with_params)

    # Diff with previous
    os.makedirs("data", exist_ok=True)
    url_store = os.path.join("data", f"{domain}_all.txt")
    prev_urls = set()
    if os.path.exists(url_store):
        with open(url_store, "r", encoding="utf-8", errors="ignore") as f:
            prev_urls = set(l.strip() for l in f if l.strip())
    new_urls = [u for u in urls if u not in prev_urls]
    with open(url_store, "w", encoding="utf-8") as f:
        f.write("\n".join(urls))

    url_status = []
    if status and urls:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futs = [ex.submit(check_url, u) for u in urls]
            for ft in as_completed(futs):
                url_status.append(ft.result())

    subs = []
    new_subs = []
    sub_status = []
    if scan_subs:
        subs = extract_subdomains(urls, domain)
        sub_store = os.path.join("data", f"{domain}_subs.txt")
        prev_subs = set()
        if os.path.exists(sub_store):
            with open(sub_store, "r", encoding="utf-8", errors="ignore") as f:
                prev_subs = set(l.strip() for l in f if l.strip())
        new_subs = [s for s in subs if s not in prev_subs]
        with open(sub_store, "w", encoding="utf-8") as f:
            f.write("\n".join(subs))
        if status and subs:
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futs = [ex.submit(check_url, f"http://{s}") for s in subs]
                for ft in as_completed(futs):
                    sub_status.append(ft.result())

    return render_template("results.html",
                           domain=domain,
                           counts={"urls": len(urls), "new_urls": len(new_urls),
                                   "subs": len(subs), "new_subs": len(new_subs)},
                           urls=urls, new_urls=new_urls,
                           url_status=url_status,
                           subs=subs, new_subs=new_subs, sub_status=sub_status,
                           include_cc=include_cc, with_params=with_params, exts=exts or [],
                           status=status, scan_subs=scan_subs, threads=threads)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
