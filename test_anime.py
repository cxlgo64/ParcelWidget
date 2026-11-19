import datetime

from features.anime import merge, parse_home, roll, stats, week_dates

PAGE = """
<div class="sk-col date-text"> 2026 &#x79CB;&#x5B63;&#x756A;&#x7EC4; <span class="caret"></span></div>
<div class="sk-bangumi" data-dayofweek="4"> <div class="row"> &#x661F;&#x671F;&#x56DB; </div>
 <ul class="an-ul"><li> <span data-src="/images/Bangumi/1/a.jpg?width=400" class="b-lazy"></span>
  <div class="date-text">2026/11/19 &#x66F4;&#x65B0;</div>
  <a href="/Home/Bangumi/101" target="_blank" class="an-text" title="&#x756A;A">x</a></li>
 <li> <span data-src="/images/Bangumi/1/b.jpg" class="b-lazy"></span>
  <div class="date-text">2026/11/12 &#x66F4;&#x65B0;</div>
  <a href="/Home/Bangumi/102" target="_blank" class="an-text" title="B">x</a></li></ul></div>
<div class="sk-bangumi" data-dayofweek="0"> <div class="row"> Sunday </div>
 <ul class="an-ul"><li> <span data-src="/images/Bangumi/1/c.jpg" class="b-lazy"></span>
  <div class="date-text">2026/11/16 &#x66F4;&#x65B0;</div>
  <a href="/Home/Bangumi/103" target="_blank" class="an-text" title="C">x</a></li></ul></div>
<div class="sk-bangumi" data-dayofweek="7"> <div class="row"> Movie </div>
 <ul class="an-ul"><li> <span data-src="/images/Bangumi/1/d.jpg" class="b-lazy"></span>
  <div class="date-text">2026/11/19 &#x66F4;&#x65B0;</div>
  <a href="/Home/Bangumi/104" target="_blank" class="an-text" title="D">x</a></li></ul></div>
"""
THU = datetime.date(2026, 11, 19)        # a Thursday


def test_parse():
    g = parse_home(PAGE, "https://mikanani.me")
    assert g["season"] == "2026 秋季番组"
    by = {s["id"]: s for s in g["shows"]}
    assert by["101"]["title"] == "番A" and by["101"]["day"] == 3          # Mikan 4 (Thursday) -> 3
    assert by["103"]["day"] == 6 and by["104"]["day"] == 7                # Sunday -> 6, movie stays 7
    assert by["101"]["updated"] == "2026-11-19"
    assert by["101"]["url"] == "https://mikanani.me/Home/Bangumi/101"
    assert by["101"]["cover"].startswith("https://mikanani.me/images/Bangumi/1/a.jpg?width=120")


def test_week():
    w = week_dates(THU)
    assert w[3] == "2026-11-19" and w[0] == "2026-11-16" and w[4] == "2026-11-13" and w[6] == "2026-11-15"


def test_merge_and_stats():
    g = parse_home(PAGE)
    days = {}
    added = merge(days, g["shows"], THU)
    assert sorted(added) == ["101", "104"]                # out today
    assert set(days["3"]["items"]) == {"101", "104"}      # Thursday
    assert set(days["0"]["items"]) == {"103"}             # out on Monday the 16th
    assert "102" not in str(days)                         # 2026-11-12: older than 7 days
    assert merge(days, g["shows"], THU) == []             # nothing new the second time
    st = stats(days, g["shows"], THU)
    assert st["updated"] == 2 and st["scheduled"] == 2 and st["pending"] == 1 and st["week"] == 3


def test_same_weekday_next_week_replaces_last_week():
    days = {}
    merge(days, parse_home(PAGE)["shows"], THU)
    next_thu = THU + datetime.timedelta(days=7)
    assert roll(days, next_thu)                           # last Thursday's day is cleared
    assert days["3"] == {"date": "2026-11-26", "items": {}}
    assert days["0"]["date"] == "2026-11-23" and days["0"]["items"] == {}
    nxt = [{"id": "201", "title": "E", "url": "u", "cover": "", "day": 3, "updated": "2026-11-26"}]
    assert merge(days, nxt, next_thu) == ["201"]
    assert set(days["3"]["items"]) == {"201"}


def test_kept_through_the_week():
    days = {}
    merge(days, parse_home(PAGE)["shows"], THU)
    fri = THU + datetime.timedelta(days=1)
    roll(days, fri)                                       # Friday: Thursday stays, last Friday goes
    assert set(days["3"]["items"]) == {"101", "104"} and days["4"]["date"] == "2026-11-20"
