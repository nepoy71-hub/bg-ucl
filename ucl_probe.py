"""ucl_probe.py - проверка на UCL/UEL в новия формат в живата памет (само чете)

Стои до euroberth.py и ползва неговия достъп до процеса.  Иска пусната игра
със заредена кариера.  Нищо не пише в играта, освен с --apply. Изходът се записва и в probe_<команда>.txt до скрипта.

    py ucl_probe.py            състоянието на всички фази на UCL и UEL
    py ucl_probe.py dups       всеки клуб с два мача на една и съща дата
    py ucl_probe.py ko         1/8-финалите с мястото на всеки клуб в лиговата фаза
    py ucl_probe.py diary      дневниците на клубовете за дните 90-130 (или: diary 250 364), и редовете без мач
    py ucl_probe.py agenda     дневният ред по дни (редовете без мач в календара): agenda 250 364
    py ucl_probe.py diaryfix   поправя дневник, който сочи чужд мач (само показва; с --apply пише)
    py ucl_probe.py bg         къде е всеки клуб от българската първа лига в Европа
    py ucl_probe.py tables     изиграни мачове и точки в класиранията (натрупване?)
    py ucl_probe.py selfcarry  спира пренасянето на точки на редовния сезон сам към себе си (--apply)
    py ucl_probe.py super      двете суперкупи (7 и 88) и откъде идват участниците им
    py ucl_probe.py fields     полетата за сдвояване лига+купа за Суперкупата (България/Испания/Белгия/Англия)
    py ucl_probe.py slots      местата на клубовете по състезания за рег 152 (или: slots 152 81)
    py ucl_probe.py slotfix    нулира старите числа на българските фази в местата на клубовете (--apply)
    py ucl_probe.py extras     неизиграните мачове на лиговата фаза и откъде са клубовете им
    py ucl_probe.py grpday     денят на първия кръг на групите 153/154 (grpday 80 --apply го мести, само в паметта)
    py ucl_probe.py rounds     кръговете на състезанията в общия склад и дали някой запис е споделен
    py ucl_probe.py events     всички мачове на 152/153/154/170/171/173 (стари и нови) и дните в календара
    py ucl_probe.py stalefix   маха от календара старите мачове на българските фази (--apply)
    py ucl_probe.py health     колко са заети складовете: мачове (13000), кръгове (2000), класирания (600)
    py ucl_probe.py snap       снимка на края на сезона (преди 30.06) в season_snap.json
    py ucl_probe.py verify     след 01.07: изпадане/промоция/суперкупа/Европа спрямо снимката
    py ucl_probe.py days       по кои дни играе лиговата фаза и колко мача има всеки ден
"""
import struct
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import euroberth as E

BASE = [0]
TBD = 0xFFFFFFFF >> 14      # мястото "още не е изтеглен" в бъдещите кръгове на купите

PHASES = [
    (2,    "UCL плейоф (авг. / 9-24 февр.)"),
    (3,    "UCL"),
    (1027, "UCL лигова фаза"),
    (4,    "UCL елиминации"),
    (5,    "UEL"),
    (1029, "UEL лигова фаза"),
    (188,  "UEL плейоф 9-24"),
    (6,    "UEL елиминации"),
]


_NAMES = None


def nm(c):
    """името на клуба от map_teams.txt (до скрипта), иначе номера"""
    global _NAMES
    if _NAMES is None:
        import os
        _NAMES = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_teams.txt")
        try:
            for line in open(path, encoding="utf-8-sig", errors="replace"):
                m = __import__("re").match(r"\s*(\d+)\s*,.*#\s*(.+?)\s*$", line)
                if m:
                    _NAMES.setdefault(int(m.group(1)), m.group(2))
        except OSError:
            pass
    if c is None:
        return "-"
    return _NAMES.get(c, str(c))


def attach():
    pid, err = E.find_pid()
    if err:
        raise SystemExit(err)
    p = E.Proc(pid)
    base = p.base()
    return p, base, E.model_of(p, base)


def comp_block(p, model):
    blob = p.read(model + E.COMP_OFF, E.COMP_N * E.COMP_REC)
    if not blob:
        raise SystemExit("не мога да прочета състезанията")
    return blob


def comp_info(blob, cid):
    for i in range(E.COMP_N):
        o = i * E.COMP_REC
        if struct.unpack_from("<H", blob, o)[0] == cid:
            n = struct.unpack_from("<H", blob, o + E.C_COUNT)[0] & 0x7F
            f304 = struct.unpack_from("<I", blob, o + 0x304)[0]
            return {"n": n, "drawn": (f304 >> 8) & 1}
    return None


def all_events(p, model):
    blob = p.read(model + E.EVENT_OFF, E.EVENT_N * E.EVENT_REC)
    if not blob:
        raise SystemExit("не мога да прочета мачовете")
    out = []
    for i in range(E.EVENT_N):
        o = i * E.EVENT_REC
        if struct.unpack_from("<H", blob, o)[0] != i:
            continue
        pk = struct.unpack_from("<I", blob, o + E.E_PACKED)[0]
        comp = pk & 0xFFFF
        if comp == 0xFFFF or comp == 0:
            continue
        out.append({
            "id": i, "comp": comp, "played": bool(pk & E.PLAYED_BIT),
            "year": struct.unpack_from("<H", blob, o + E.E_YEAR)[0],
            "mon": blob[o + E.E_MON], "day": blob[o + E.E_DAY],
            "home": struct.unpack_from("<I", blob, o + E.E_HOME)[0] >> E.TEAM_SHIFT,
            "away": struct.unpack_from("<I", blob, o + E.E_AWAY)[0] >> E.TEAM_SHIFT,
        })
    return out


def base_comp(c):
    return c & 0x3FF if c > 1024 and (c & 0x3FF) in (2, 188) else c


def cmd_state(p, model):
    print("в играта е", E.today(p, model))
    blob = comp_block(p, model)
    ev = all_events(p, model)
    by = defaultdict(list)
    for e in ev:
        by[base_comp(e["comp"])].append(e)
    for cid, name in PHASES:
        info = comp_info(blob, cid)
        if info is None:
            print("  %-5d %-32s НЯМА в живия модел" % (cid, name))
            continue
        ms = by.get(cid, [])
        played = sum(1 for e in ms if e["played"])
        dates = sorted({(e["year"], e["mon"], e["day"]) for e in ms if e["mon"]})
        span = ""
        if dates:
            a, z = dates[0], dates[-1]
            span = "  %02d.%02d.%d - %02d.%02d.%d, %d дати" % (a[2], a[1], a[0], z[2], z[1], z[0], len(dates))
        print("  %-5d %-32s клубове %2d  изтеглено %d  мачове %3d (изиграни %3d)%s"
              % (cid, name, info["n"], info["drawn"], len(ms), played, span))
    for cid in (1027, 1029):
        ms = by.get(cid, [])
        if not ms:
            continue
        cnt = defaultdict(int)
        for e in ms:
            cnt[e["home"]] += 1
            cnt[e["away"]] += 1
        per = sorted(set(cnt.values()))
        print("  %d: мачове на клуб %s (трябва 8 за всеки)" % (cid, per))


def cmd_dups(p, model):
    print("в играта е", E.today(p, model))
    ev = all_events(p, model)
    seen = defaultdict(list)
    for e in ev:
        if not e["mon"]:
            continue
        for club in (e["home"], e["away"]):
            if club and club != TBD:
                seen[(club, e["year"], e["mon"], e["day"])].append(e)
    bad = [(k, v) for k, v in seen.items() if len(v) > 1]
    if not bad:
        print("няма клуб с два мача на една дата (%d мача проверени)" % len(ev))
        return
    print("%d случая на два мача в един ден:" % len(bad))
    for (club, y, mo, d), v in sorted(bad, key=lambda x: (x[0][1], x[0][2], x[0][3])):
        print("  клуб %-6d %02d.%02d.%d  състезания %s" % (club, d, mo, y, ", ".join(str(e["comp"]) for e in v)))
        if "-v" in sys.argv:
            for e in v:
                print("        мач %5d  комп %5d  %6d - %-6d  %s" % (e["id"], e["comp"], e["home"], e["away"],
                                                                "изигран" if e["played"] else "неизигран"))
    if "-v" in sys.argv:
        yrs = defaultdict(lambda: [0, 0])
        for e in ev:
            if base_comp(e["comp"]) in (1027, 1029) and e["mon"]:
                yrs[(e["comp"], e["year"])][0] += 1
                yrs[(e["comp"], e["year"])][1] += e["played"]
        for (c, y), (n, pl) in sorted(yrs.items()):
            print("  %d, година %d: %d мача, изиграни %d" % (c, y, n, pl))


def cmd_days(p, model):
    ev = all_events(p, model)
    for cid in (1027, 1029):
        cnt = defaultdict(int)
        for e in ev:
            if e["comp"] == cid and e["mon"]:
                cnt[(e["year"], e["mon"], e["day"])] += 1
        print("%d:" % cid)
        for (y, mo, d), n in sorted(cnt.items()):
            print("  %02d.%02d.%d  %d мача" % (d, mo, y, n))


def table_ranks(p, cid):
    """{клуб: място} от класирането на лиговата фаза (веригата на euroberth)."""
    S = struct.unpack("<Q", p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8))[0]
    blob = p.read(S + E.STAND_BASE, E.STAND_N * E.STAND_REC)
    rec, best = None, -1
    for i in range(E.STAND_N):
        o = i * E.STAND_REC
        if struct.unpack_from("<H", blob, o)[0] != cid:
            continue
        year = struct.unpack_from("<H", blob, o + 2)[0]
        if year > best:
            best, rec = year, S + E.STAND_BASE + o
    if rec is None:
        return {}
    n = struct.unpack("<I", p.read(rec + E.ST_COUNT, 4))[0]
    if not 0 < n <= 64:
        return {}
    raw = p.read(rec + E.ST_ROWS, n * E.ST_STRIDE)
    out = {}
    for k in range(n):
        row = raw[k * E.ST_STRIDE:(k + 1) * E.ST_STRIDE]
        club = struct.unpack_from("<I", row, 0)[0] >> E.TEAM_SHIFT
        out[club] = k + 1
    return out


def cmd_ko(p, model):
    print("в играта е", E.today(p, model))
    for name, row, ko in (("UCL", 1027, 4), ("UEL", 1029, 6)):
        ranks = table_ranks(p, row)
        lst = E.participants(p, model, ko)
        if not lst:
            print("%s: регулация %d е празна" % (name, ko))
            continue
        print("%s 1/8-финали (регулация %d), място в лиговата фаза:" % (name, ko))
        for i in range(0, len(lst) - 1, 2):
            a, b = lst[i] >> E.TEAM_SHIFT, lst[i + 1] >> E.TEAM_SHIFT
            print("  двойка %d: %s (%s)  срещу  %s (%s)"
                  % (i // 2 + 1, nm(a), ranks.get(a, "?"), nm(b), ranks.get(b, "?")))


def cmd_diary(p, model):
    """дневниците (32 клубни програми) за дните 90-130 и мачът, към който сочи всеки запис"""
    print("в играта е", E.today(p, model))
    ev = {e["id"]: e for e in all_events(p, model)}
    lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (90, 130)
    for i in range(E.AG_SLOTS):
        at = model + E.CALENDAR + E.AG_BASE + i * E.AG_STRIDE
        raw = struct.unpack("<I", p.read(at + E.AG_CLUB, 4))[0]
        club = raw >> E.TEAM_SHIFT
        if raw == 0xFFFFFFFF or club == 0:
            continue
        blob = p.read(at + E.AG_HEAD, 365 * E.AG_REC)
        lines = []
        for d in range(lo, hi + 1):
            o = d * E.AG_REC
            mid, comp = struct.unpack_from("<HH", blob, o)
            if mid == 0xFFFF and comp == 0xFFFF:
                continue
            rnd, two, c = struct.unpack_from("<III", blob, o + 4)
            e = ev.get(mid)
            if mid == 0xFFFF:
                m, bad = "без мач", "   <-- ред в календара без съперник"
            else:
                m = "мач %d: %d - %d (комп %d)" % (mid, e["home"], e["away"], e["comp"]) if e else "мач %d: НЯМА" % mid
                bad = "" if e and club in (e["home"], e["away"]) else "   <-- клубът не е в този мач"
            lines.append("    ден %3d  комп %-5d кръг %-4d +8=%d  +C=%08x (%d)  %s%s"
                         % (d, comp, rnd, two, c, c >> E.TEAM_SHIFT, m, bad))
        if lines:
            print("клуб %d (слот %d, суров %08x)" % (club, i, raw))
            print("\n".join(lines))


def cmd_agenda(p, model):
    """дневният ред на всеки ден (18 слота на +0x234 в записа на деня): u16 вид, u16 параметър,
    u16 година, u8 месец, u8 ден; празен = вид 0x3F. До всеки ден: колко мача на 1027/1029 има
    в деня и дали клубът от слот 0 на дневниците играе. Само чете.
        agenda 250 364     или през Нова година: agenda 250 40"""
    print("в играта е", E.today(p, model))
    ev = {e["id"]: e for e in all_events(p, model)}
    lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (250, 364)
    days = list(range(lo, hi + 1)) if lo <= hi else list(range(lo, 365)) + list(range(0, hi + 1))
    at = model + E.CALENDAR + E.AG_BASE
    me = struct.unpack("<I", p.read(at + E.AG_CLUB, 4))[0] >> E.TEAM_SHIFT
    print("клуб от слот 0: %d (%s)" % (me, nm(me)))
    for d in days:
        rec = p.read(model + E.CALENDAR + d * 0x2C4, 0x2C4)
        if not rec:
            continue
        cnt = struct.unpack_from("<H", rec, 0x230)[0]
        ids = struct.unpack_from("<%dH" % min(cnt, 280), rec, 0) if cnt <= 280 else ()
        euro = defaultdict(int)
        mine = []
        for i in ids:
            e = ev.get(i)
            if not e:
                continue
            if e["comp"] in (1027, 1029):
                euro[e["comp"]] += 1
            if me in (e["home"], e["away"]):
                mine.append("%d %s-%s (комп %d)" % (i, nm(e["home"]), nm(e["away"]), e["comp"]))
        slots = []
        for k in range(18):
            kind, par, yr, mo, dd = struct.unpack_from("<HHHBB", rec, 0x234 + 8 * k)
            if kind == 0x3F:
                continue
            slots.append("вид %d парам %d (%02d.%02d.%d)" % (kind, par, dd, mo, yr))
        if not slots and not euro and not mine:
            continue
        print("ден %3d  мачове %3d  1027:%-2d 1029:%-2d  %s" % (d, cnt, euro[1027], euro[1029],
              ("клубът: " + "; ".join(mine)) if mine else "клубът не играе"))
        for s_ in slots:
            print("          ред: " + s_)


def cmd_diaryfix(p, model):
    """дневник, който сочи мач без клуба -> мачът на същия ден и в същото състезание, в който
    клубът е; без --apply само показва"""
    apply = "--apply" in sys.argv
    print("в играта е", E.today(p, model))
    evs = all_events(p, model)
    ev = {e["id"]: e for e in evs}
    year = struct.unpack("<H", p.read(model + E.CALENDAR + E.CAL_DAY + 2, 2))[0]
    n = 0
    for i in range(E.AG_SLOTS):
        at = model + E.CALENDAR + E.AG_BASE + i * E.AG_STRIDE
        raw = struct.unpack("<I", p.read(at + E.AG_CLUB, 4))[0]
        club = raw >> E.TEAM_SHIFT
        if raw == 0xFFFFFFFF or club == 0:
            continue
        blob = p.read(at + E.AG_HEAD, 365 * E.AG_REC)
        for d in range(365):
            o = d * E.AG_REC
            mid, comp = struct.unpack_from("<HH", blob, o)
            if mid == 0xFFFF:
                continue
            e = ev.get(mid)
            if not e or club in (e["home"], e["away"]):
                continue
            cands = [x for x in evs if x["comp"] == comp and club in (x["home"], x["away"])
                     and (x["year"], x["mon"], x["day"]) == (e["year"], e["mon"], e["day"])]
            if len(cands) != 1:
                print("  клуб %d ден %d: мач %d е чужд, но не намирам точно един заместник (%d)" % (club, d, mid, len(cands)))
                continue
            new = cands[0]
            print("  клуб %d ден %d: мач %d (%d - %d) -> мач %d (%d - %d)%s"
                  % (club, d, mid, e["home"], e["away"], new["id"], new["home"], new["away"],
                     "" if apply else "   [без --apply нищо не е записано]"))
            if apply:
                ok = p.write(at + E.AG_HEAD + o, struct.pack("<H", new["id"]))
                back = struct.unpack("<H", p.read(at + E.AG_HEAD + o, 2))[0]
                print("      записано" if ok and back == new["id"] else "      ЗАПИСЪТ НЕ МИНА")
            n += 1
    if not n:
        print("всички записи в дневниците сочат мачове на собствения клуб")


def cmd_bg(p, model):
    """къде е всеки клуб от българската първа лига (20 / 152) в европейските турнири"""
    print("в играта е", E.today(p, model))
    clubs = []
    for reg in (20, 152):
        for raw in E.participants(p, model, reg) or []:
            c = raw >> E.TEAM_SHIFT
            if c not in clubs:
                clubs.append(c)
    where = {}
    for cid, name in PHASES:
        for i, raw in enumerate(E.participants(p, model, cid) or []):
            where.setdefault(raw >> E.TEAM_SHIFT, []).append("%s (%d.)" % (name, i + 1))
    found = False
    for c in clubs:
        if c in where:
            found = True
            print("  %-20s %s" % (nm(c), ", ".join(where[c])))
    if not found:
        print("  нито един български клуб не е в европейски турнир (още не е раздадено?)")


def cmd_tables(p, model):
    """всички записи на класирането за всяка регулация: изиграни мачове и точки"""
    print("в играта е", E.today(p, model))
    regs = [int(x) for x in sys.argv[2:]] or [20, 152, 153, 154, 81, 1027, 1029]
    sp = p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8)
    S = struct.unpack("<Q", sp)[0]
    blob = p.read(S + E.STAND_BASE, E.STAND_N * E.STAND_REC)
    for reg in regs:
        hits = 0
        for i in range(E.STAND_N):
            o = i * E.STAND_REC
            if struct.unpack_from("<H", blob, o)[0] != reg:
                continue
            hits += 1
            n = struct.unpack_from("<I", blob, o + E.ST_COUNT)[0]
            if not 0 < n <= 64:
                print("  рег %-5d запис %3d  редове %d" % (reg, i, n))
                continue
            pl = [blob[o + E.ST_ROWS + k * E.ST_STRIDE + 0x0F] for k in range(n)]
            pts = [blob[o + E.ST_ROWS + k * E.ST_STRIDE + 8] for k in range(n)]
            top = struct.unpack_from("<I", blob, o + E.ST_ROWS)[0] >> E.TEAM_SHIFT
            head = blob[o + 2:o + 0x14].hex(" ")
            print("  рег %-5d запис %3d  %2d отбора  изиграни %d..%d  точки до %d  (първи: клуб %d)  глава %s"
                  % (reg, i, n, min(pl), max(pl), max(pts), top, head))
        if not hits:
            print("  рег %-5d няма запис" % reg)


SELF_RVA = 0x134A65D
SELF_OLD = bytes.fromhex("0fb71bb8ffff0000663bd80f843c020000")
SELF_NEW = bytes.fromhex("0fb71b663b1e742166" "83fbff741b0f1f00")
BGL_RVA = 0x134A66E
BGL_CARRY = bytes.fromhex("b8089000000fa3f87216b8000900000fa3f80f8210010000e91f0200000f1f00")


def cmd_selfcarry(p, model):
    """при строежа на редовния сезон (вид 12) той пренасяше точки сам към себе си от миналия
    сезон; кръпката прескача пренасянето, когато източникът е самата фаза. Само в паметта."""
    base = BASE[0]
    cur = p.read(base + SELF_RVA, len(SELF_OLD))
    bgl = p.read(base + BGL_RVA, len(BGL_CARRY))
    if cur == SELF_NEW:
        print("кръпката вече стои (0x%X)" % (0x140000000 + SELF_RVA))
        return
    if cur != SELF_OLD:
        print("на 0x%X стои нещо непознато - НЕ пипам: %s" % (0x140000000 + SELF_RVA, cur.hex()))
        return
    if bgl != BGL_CARRY:
        print("кръпката на bg_link за пренасянето (0x%X) не стои - без нея тази не бива да се слага"
              % (0x140000000 + BGL_RVA))
        return
    if "--apply" not in sys.argv:
        print("всичко съвпада; с --apply кръпката се слага на 0x%X" % (0x140000000 + SELF_RVA))
        return
    ok = p.write(base + SELF_RVA, SELF_NEW)
    back = p.read(base + SELF_RVA, len(SELF_NEW))
    print("сложена" if ok and back == SELF_NEW else "ЗАПИСЪТ НЕ МИНА")


def cmd_super(p, model):
    """двете суперкупи и откъде идват участниците им: 7 (UEFA: победителите на 4 и 6), 88 (България)"""
    print("в играта е", E.today(p, model))
    blob = comp_block(p, model)
    ev = all_events(p, model)
    for cid, name in ((7, "Суперкупа на UEFA"), (88, "Суперкупа на България"),
                      (4, "UCL елиминации"), (6, "UEL елиминации"), (26, "Купа на България")):
        info = comp_info(blob, cid)
        if info is None:
            print("  %-4d %-24s НЯМА в живия модел" % (cid, name))
            continue
        lst = [r >> E.TEAM_SHIFT for r in (E.participants(p, model, cid) or [])]
        ms = [e for e in ev if e["comp"] == cid]
        dates = sorted({"%02d.%02d.%d" % (e["day"], e["mon"], e["year"]) for e in ms if e["mon"]})
        print("  %-4d %-24s клубове %2d %s  изтеглено %d  мачове %d %s"
              % (cid, name, info["n"], lst[:4], info["drawn"], len(ms), ", ".join(dates[:4])))


def cmd_fields(p, model):
    """полетата, по които играта сдвоява лига и купа за Суперкупата (0x141362980):
    категория (+0x300 битове 25-28, трябва 5), формат (+0x308 битове 23-28, лигата трябва 1/6/11),
    държава (+0x30C), и редът в масива на състезанията"""
    blob = comp_block(p, model)
    groups = [("България", [20, 152, 153, 154, 81, 26, 88]),
              ("Испания", [19, 80, 25, 87]),
              ("Белгия", [155, 156, 157, 158, 122, 128]),
              ("Англия", [17, 79, 23, 86])]
    for gname, regs in groups:
        print(gname)
        for reg in regs:
            for i in range(E.COMP_N):
                o = i * E.COMP_REC
                if struct.unpack_from("<H", blob, o)[0] != reg:
                    continue
                f300 = struct.unpack_from("<I", blob, o + 0x300)[0]
                f304 = struct.unpack_from("<I", blob, o + 0x304)[0]
                f308 = struct.unpack_from("<I", blob, o + 0x308)[0]
                f30c = struct.unpack_from("<I", blob, o + 0x30C)[0]
                print("  рег %-4d слот %3d  категория %2d  формат %2d  +0x30C %08x  +0x304 %08x  +0x80 %d"
                      % (reg, i, (f300 >> 25) & 0xF, (f308 >> 23) & 0x3F, f30c, f304,
                         struct.unpack_from("<I", blob, o + 0x80)[0]))
                break
            else:
                print("  рег %-4d НЯМА" % reg)


CLUB_OFF, CLUB_REC, SLOT_OFF, SLOT_N, SLOT_SZ = 0xADF4BC, 0x690, 0x2EC, 15, 0x14


def cmd_slots(p, model):
    """местата на клубовете по състезания (15 x 0x14 от +0x2EC) - по участниците на регулация"""
    print("в играта е", E.today(p, model))
    regs = [int(x) for x in sys.argv[2:]] or [152]
    blob = comp_block(p, model)
    for reg in regs:
        parts = None
        for i in range(E.COMP_N):
            o = i * E.COMP_REC
            if struct.unpack_from("<H", blob, o)[0] == reg:
                n = struct.unpack_from("<H", blob, o + E.C_COUNT)[0] & 0x7F
                parts = [struct.unpack_from("<I", blob, o + E.C_PARTS + 4 * k)[0] for k in range(n)]
                break
        if parts is None:
            print("рег %d: няма запис" % reg)
            continue
        print("рег %d: %d участници" % (reg, len(parts)))
        for raw in parts:
            idx = raw & 0x3FFF
            at = model + CLUB_OFF + idx * CLUB_REC
            rec = p.read(at, CLUB_REC)
            if not rec:
                print("  %08x: не се чете" % raw)
                continue
            head = struct.unpack_from("<I", rec, 0)[0]
            ok = "" if (head ^ raw) & 0xFFFFC000 == 0 else "  (главата %08x НЕ съвпада)" % head
            out = []
            for k in range(SLOT_N):
                e = rec[SLOT_OFF + k * SLOT_SZ:SLOT_OFF + (k + 1) * SLOT_SZ]
                comp = struct.unpack_from("<H", e, 0)[0]
                if comp != 0xFFFF:
                    out.append("%d[%s]" % (comp, e[2:].hex(" ")))
            print("  клуб %5d  инд %4d%s" % (raw >> 14, idx, ok))
            for x in out:
                print("        " + x)

BG_STALE = (152, 153, 154, 170, 171, 173)


def newest_played(p, reg):
    """най-много изиграни мачове в най-новия запис на класирането на регулацията"""
    S = struct.unpack("<Q", p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8))[0]
    blob = p.read(S + E.STAND_BASE, E.STAND_N * E.STAND_REC)
    best = None
    for i in range(E.STAND_N):
        o = i * E.STAND_REC
        if struct.unpack_from("<H", blob, o)[0] != reg:
            continue
        year = struct.unpack_from("<H", blob, o + 2)[0]
        n = struct.unpack_from("<I", blob, o + E.ST_COUNT)[0]
        pl = max([blob[o + E.ST_ROWS + k * E.ST_STRIDE + 0x0F] for k in range(n)] or [0]) if 0 < n <= 64 else 0
        if best is None or year > best[0]:
            best = (year, pl)
    return best


def cmd_slotfix(p, model):
    """нулира в местата на клубовете старите числа на 152/153/154/170/171/173 (номерът остава).
    Само преди първия мач от първенството в новия сезон. Пише само с --apply."""
    print("в играта е", E.today(p, model))
    nb = newest_played(p, 152)
    if nb is None:
        print("няма класиране на 152 - НЕ пипам")
        return
    print("най-новото класиране на 152: година %d, изиграни до %d" % nb)
    if nb[1] != 0:
        print("в новия сезон вече има изигран мач от 152 - НЕ пипам (зареди запис отпреди първия мач)")
        return
    n = struct.unpack("<I", p.read(model + 0xD0BCEC, 4))[0]
    n = min(n, 0x2EE)
    raw = p.read(model + CLUB_OFF, n * CLUB_REC)
    fixes = []
    for i in range(n):
        for k in range(SLOT_N):
            o = i * CLUB_REC + SLOT_OFF + k * SLOT_SZ
            comp = struct.unpack_from("<H", raw, o)[0]
            if comp in BG_STALE and any(raw[o + 2:o + SLOT_SZ]):
                fixes.append((o, comp))
    cnt = defaultdict(int)
    for _, c in fixes:
        cnt[c] += 1
    print("места със стари числа: %s" % (", ".join("%d: %d" % kv for kv in sorted(cnt.items())) or "няма"))
    if not fixes or "--apply" not in sys.argv:
        if fixes:
            print("с --apply се нулират")
        return
    bad = 0
    for o, c in fixes:
        at = model + CLUB_OFF + o
        if not p.write(at + 2, bytes(SLOT_SZ - 2)) or p.read(at + 2, SLOT_SZ - 2) != bytes(SLOT_SZ - 2):
            bad += 1
    print("нулирани %d, неуспешни %d" % (len(fixes) - bad, bad))


def cmd_extras(p, model):
    """мачове на лиговата фаза (1027/1029), останали неизиграни: откъде са клубовете им"""
    print("в играта е", E.today(p, model))
    blob = comp_block(p, model)
    ev = all_events(p, model)

    def clubs_of(cid):
        for i in range(E.COMP_N):
            o = i * E.COMP_REC
            if struct.unpack_from("<H", blob, o)[0] == cid:
                n = struct.unpack_from("<H", blob, o + E.C_COUNT)[0] & 0x7F
                return [struct.unpack_from("<I", blob, o + E.C_PARTS + 4 * k)[0] >> 14 for k in range(n)]
        return []
    where = defaultdict(list)
    for cid in (2, 3, 5, 188, 1027, 1029, 4, 6):
        for pos, c in enumerate(clubs_of(cid)):
            where[c].append("%d#%d" % (cid, pos + 1))
    for cid in (1027, 1029):
        rk = table_ranks(p, cid)
        ms = [e for e in ev if e["comp"] == cid]
        ids = sorted(e["id"] for e in ms)
        un = [e for e in ms if not e["played"]]
        print("%d: %d мача (номера %d..%d), неизиграни %d" % (cid, len(ms), ids[0] if ids else 0, ids[-1] if ids else 0, len(un)))
        for e in sorted(un, key=lambda x: x["id"]):
            print("   мач %5d  %02d.%02d.%d  %6d - %-6d" % (e["id"], e["day"], e["mon"], e["year"], e["home"], e["away"]))
        shown = sorted({c for e in un for c in (e["home"], e["away"])})
        for c in shown:
            n8 = sum(1 for e in ms if e["played"] and c in (e["home"], e["away"]))
            print("      клуб %6d  място %s, изиграни %d, в: %s" % (c, rk.get(c, "-"), n8, " ".join(where.get(c, []))))


GRP_TAB, GRP_REC = 0x298F600, 12


def cmd_grpday(p, model):
    """денят на първия кръг на групите 153/154 в таблицата на екзето (само в паметта).
    grpday        показва
    grpday 80 --apply   слага ден 80. Строи се на 07.03, затова се слага преди това."""
    base = BASE[0]
    print("в играта е", E.today(p, model))
    raw = p.read(base + GRP_TAB, 7 * GRP_REC)
    for k in range(7):
        d, r, w = struct.unpack_from("<III", raw, k * GRP_REC)
        print("  запис %d: ден %d, кръг %d, среща %d" % (k, d, r, w))
    args = [a for a in sys.argv[2:] if a.isdigit()]
    if not args or "--apply" not in sys.argv:
        return
    day = int(args[0])
    d0, r0, _ = struct.unpack_from("<III", raw, 0)
    if r0 != 0 or d0 not in (79, 86):
        print("първият запис не е кръг 0 на ден 79/86 - НЕ пипам")
        return
    ok = p.write(base + GRP_TAB, struct.pack("<I", day))
    back = struct.unpack("<I", p.read(base + GRP_TAB, 4))[0]
    print("кръг 0 -> ден %d: %s" % (day, "сложено" if ok and back == day else "НЕ МИНА"))


def cmd_order(p, model):
    """редът на състезанията в паметта (масивът от 300) - за сравнение с реда в бина"""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    print("в играта е", E.today(p, model), " състезания:", n)
    ids = [struct.unpack_from("<H", blob, i * E.COMP_REC)[0] for i in range(min(n, E.COMP_N))]
    print(" ".join(str(x) for x in ids))
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        print("%3d %5d  %s" % (i, ids[i], blob[o:o + 0x10].hex(" ")))


POOL_OFF, POOL_REC, POOL_N = 0xD65F64, 0x208, 2000


def cmd_rounds(p, model):
    """кръговете (записите от 0x208 в общия склад от 2000) на всяко състезание: споделя ли се запис?"""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    pool = p.read(model + POOL_OFF, POOL_N * POOL_REC)
    print("в играта е", E.today(p, model))
    owners = defaultdict(list)
    per = {}
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        cid = struct.unpack_from("<H", blob, o)[0]
        cnt = (struct.unpack_from("<I", blob, o + 0x300)[0] >> 19) & 0x3F
        idx = [struct.unpack_from("<I", blob, o + 0x88 + 4 * k)[0] for k in range(min(cnt, 58))]
        per[cid] = idx
        for k, x in enumerate(idx):
            owners[x].append((cid, k))
    used = sum(1 for x in owners if x < POOL_N)
    print("използвани записи: %d от %d" % (used, POOL_N))
    shared = {x: v for x, v in owners.items() if len(v) > 1}
    print("записи, споделени от няколко състезания: %d" % len(shared))
    for x, v in sorted(shared.items()):
        print("   запис %5d: %s" % (x, ", ".join("%d/кръг %d" % cv for cv in v)))
    bad = [(c, k, x) for c, idx in per.items() for k, x in enumerate(idx) if x >= POOL_N]
    if bad:
        print("кръгове без запис (>= 2000): %s" % ", ".join("%d/%d=%d" % b for b in bad[:40]))
    regs = [int(a) for a in sys.argv[2:] if a.isdigit()] or [153, 154, 26, 4, 6]
    for cid in regs:
        idx = per.get(cid)
        if idx is None:
            print("%d: няма" % cid)
            continue
        print("%d: %d кръга" % (cid, len(idx)))
        for k, x in enumerate(idx):
            if x >= POOL_N:
                print("   кръг %2d -> %d (няма)" % (k, x))
                continue
            r = pool[x * POOL_REC:(x + 1) * POOL_REC]
            w = struct.unpack_from("<I", r, 0x204)[0]
            ns = w & 0xFF
            sl = []
            for s_ in range(min(ns, 16)):
                h, a = struct.unpack_from("<II", r, 4 + 32 * s_)
                m1, m2 = struct.unpack_from("<HH", r, 4 + 32 * s_ + 8)
                sl.append("%d-%d[%d,%d]" % (h >> 14, a >> 14, m1, m2))
            print("   кръг %2d -> запис %4d  вид %2d  слотове %2d  %s" % (k, x, w >> 26, ns, " ".join(sl)))


def cmd_comp(p, model):
    """пълните записи (0x314) на състезанията - за сравнение поле по поле"""
    blob = comp_block(p, model)
    regs = [int(a) for a in sys.argv[2:] if a.isdigit()] or [20, 152, 153, 154, 26, 3, 5, 1027, 1029, 2, 188, 1212, 4, 6, 115, 155, 156, 157, 158, 81]
    print("в играта е", E.today(p, model))
    for cid in regs:
        for i in range(E.COMP_N):
            o = i * E.COMP_REC
            if struct.unpack_from("<H", blob, o)[0] == cid:
                r = blob[o:o + E.COMP_REC]
                print("== %d" % cid)
                for k in range(0, E.COMP_REC, 32):
                    print("  %03x: %s" % (k, r[k:k + 32].hex(" ")))
                break
        else:
            print("== %d няма" % cid)


def cmd_events(p, model):
    """всички мачове на дадени регулации в паметта (стари и нови) и дните в календара, които ги сочат"""
    regs = [int(a) for a in sys.argv[2:] if a.isdigit()] or [152, 153, 154, 170, 171, 173]
    print("в играта е", E.today(p, model))
    ev = all_events(p, model)
    cal = p.read(model + 0x16038A8, 365 * 0x2C4)
    onday = defaultdict(list)
    for dd in range(365):
        o = dd * 0x2C4
        n = struct.unpack_from("<H", cal, o + 0x230)[0]
        for k in range(min(n, 0x118)):
            onday[struct.unpack_from("<H", cal, o + 2 * k)[0]].append(dd)
    for cid in regs:
        ms = sorted((e for e in ev if e["comp"] == cid), key=lambda x: x["id"])
        print("%d: %d мача" % (cid, len(ms)))
        for e in ms:
            print("   мач %5d  %02d.%02d.%d  %s - %s  %s  в календара: %s" % (
                e["id"], e["day"], e["mon"], e["year"], nm(e["home"]), nm(e["away"]),
                "изигран  " if e["played"] else "неизигран", ",".join(str(x) for x in onday.get(e["id"], [])) or "-"))


def cmd_stalefix(p, model):
    """маха от календара мачовете на 152/153/154/170/171/173 от миналия сезон (онези, които
    не са в програмата на нито един сегашен кръг). Без --apply само показва."""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    pool = p.read(model + POOL_OFF, POOL_N * POOL_REC)
    print("в играта е", E.today(p, model))
    live = set()
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        cid = struct.unpack_from("<H", blob, o)[0]
        if cid not in BG_STALE:
            continue
        cnt = (struct.unpack_from("<I", blob, o + 0x300)[0] >> 19) & 0x3F
        for k in range(min(cnt, 58)):
            x = struct.unpack_from("<I", blob, o + 0x88 + 4 * k)[0]
            if x >= POOL_N:
                continue
            r = pool[x * POOL_REC:(x + 1) * POOL_REC]
            ns = struct.unpack_from("<I", r, 0x204)[0] & 0xFF
            for s_ in range(min(ns, 16)):
                live.update(struct.unpack_from("<HH", r, 4 + 32 * s_ + 8))
    stale = {e["id"] for e in all_events(p, model) if e["comp"] in BG_STALE and e["id"] not in live}
    print("мачове от миналия сезон: %d" % len(stale))
    cal_at = model + 0x16038A8
    cal = bytearray(p.read(cal_at, 365 * 0x2C4))
    hits, days = 0, []
    for dd in range(365):
        o = dd * 0x2C4
        c = struct.unpack_from("<H", cal, o + 0x230)[0]
        if c > 0x118:
            continue
        ids = [struct.unpack_from("<H", cal, o + 2 * k)[0] for k in range(c)]
        keep = [x for x in ids if x not in stale]
        if len(keep) != len(ids):
            hits += len(ids) - len(keep)
            days.append((dd, keep, c))
    print("записи в календара за махане: %d в %d дни" % (hits, len(days)))
    if not days or "--apply" not in sys.argv:
        if days:
            print("с --apply се махат (само от календара; самите мачове се освобождават от bg_ucl на 30.06)")
        return
    bad = 0
    for dd, keep, c in days:
        o = dd * 0x2C4
        body = b"".join(struct.pack("<H", x) for x in keep) + b"\xff\xff" * (c - len(keep))
        ok1 = p.write(cal_at + o, body)
        ok2 = p.write(cal_at + o + 0x230, struct.pack("<H", len(keep)))
        if not (ok1 and ok2):
            bad += 1
    print("готово: %d дни поправени, %d неуспешни" % (len(days) - bad, bad))


def cmd_health(p, model):
    """колко са заети складовете на играта: мачове (13000), кръгове (2000), класирания (600)"""
    print("в играта е", E.today(p, model))
    ev = p.read(model + E.EVENT_OFF, E.EVENT_N * E.EVENT_REC)
    used = 0
    per = defaultdict(lambda: [0, 0])
    for i in range(E.EVENT_N):
        o = i * E.EVENT_REC
        if struct.unpack_from("<H", ev, o)[0] != i:
            continue
        c = struct.unpack_from("<I", ev, o + E.E_PACKED)[0] & 0xFFFF
        if c in (0, 0xFFFF):
            continue
        used += 1
        per[c][0] += 1
        per[c][1] += (ev[o + 7] & 0x40) != 0
    print("мачове: %d от %d заети" % (used, E.EVENT_N))
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    runtime = set()
    rounds = set()
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        runtime.add(struct.unpack_from("<H", blob, o)[0])
        cnt = (struct.unpack_from("<I", blob, o + 0x300)[0] >> 19) & 0x3F
        for k in range(min(cnt, 58)):
            x = struct.unpack_from("<I", blob, o + 0x88 + 4 * k)[0]
            if x < POOL_N:
                rounds.add(x)
    pool = p.read(model + POOL_OFF, POOL_N * POOL_REC)
    nonempty = sum(1 for x in range(POOL_N) if any(pool[x * POOL_REC:x * POOL_REC + 0x10]) and pool[x * POOL_REC:x * POOL_REC + 4] != b"\xff\xff\xff\xff")
    print("кръгове: %d от %d сочени от състезанията (%d записа с данни)" % (len(rounds), POOL_N, nonempty))
    S = struct.unpack("<Q", p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8))[0]
    sb = p.read(S + E.STAND_BASE, E.STAND_N * E.STAND_REC)
    years = defaultdict(int)
    srec = 0
    for i in range(E.STAND_N):
        o = i * E.STAND_REC
        reg = struct.unpack_from("<H", sb, o)[0]
        if reg in (0, 0xFFFF):
            continue
        srec += 1
        years[struct.unpack_from("<H", sb, o + 2)[0]] += 1
    print("класирания: %d от %d заети, по години: %s" % (srec, E.STAND_N,
          ", ".join("%d: %d" % kv for kv in sorted(years.items()))))
    orphans = sorted((c, v) for c, v in per.items() if c not in runtime)
    if orphans:
        print("мачове на състезания, които ги няма: %s" % ", ".join("%d: %d" % (c, v[0]) for c, v in orphans))
    top = sorted(per.items(), key=lambda kv: -kv[1][0])[:15]
    print("най-много мачове: %s" % ", ".join("%d: %d (изиграни %d)" % (c, v[0], v[1]) for c, v in top))


def newest_table(p, reg):
    """редът на клубовете в най-новото класиране на регулацията: [(клуб, точки, изиграни)]"""
    S = struct.unpack("<Q", p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8))[0]
    blob = p.read(S + E.STAND_BASE, E.STAND_N * E.STAND_REC)
    best, rec = -1, None
    for i in range(E.STAND_N):
        o = i * E.STAND_REC
        if struct.unpack_from("<H", blob, o)[0] != reg:
            continue
        y = struct.unpack_from("<H", blob, o + 2)[0]
        if y > best:
            best, rec = y, o
    if rec is None:
        return []
    n = struct.unpack_from("<I", blob, rec + E.ST_COUNT)[0]
    if not 0 < n <= 64:
        return []
    out = []
    for k in range(n):
        r = rec + E.ST_ROWS + k * E.ST_STRIDE
        out.append((struct.unpack_from("<I", blob, r)[0] >> 14, blob[r + 8], blob[r + 0x0F]))
    return out


def tie_winner(p, model, e):
    at = model + E.EVENT_OFF + e["id"] * E.EVENT_REC
    r = p.read(at, 0x24)
    hg, ag, het, aet, hp, ap = r[0x1C], r[0x1F], r[0x1D], r[0x20], r[0x1E], r[0x21]
    if hp or ap:
        w = e["home"] if hp > ap else e["away"]
        how = "%d:%d, дузпи %d:%d" % (hg, ag, hp, ap)
    elif het or aet:
        w = e["home"] if het > aet else e["away"]
        how = "%d:%d след продължения" % (het, aet)
    else:
        w = e["home"] if hg > ag else e["away"] if ag > hg else None
        how = "%d:%d" % (hg, ag)
    return w, how


def cmd_snap(p, model):
    """снимка на края на сезона (преди 30.06): класирания, баражи, купа, участници -> season_snap.json"""
    import json, os
    snap = {"date": str(E.today(p, model))}
    for reg in (152, 153, 154, 81):
        snap["t%d" % reg] = newest_table(p, reg)
    for reg in (20, 81, 152):
        snap["p%d" % reg] = [x >> 14 for x in (E.participants(p, model, reg) or [])]
    ev = all_events(p, model)
    ties = {}
    for reg in (170, 171, 173):
        ms = [e for e in ev if e["comp"] == reg and e["played"]]
        if ms:
            e = max(ms, key=lambda x: x["id"])
            w, how = tie_winner(p, model, e)
            ties[reg] = {"home": e["home"], "away": e["away"], "winner": w, "how": how}
    snap["ties"] = ties
    cup = [e for e in ev if e["comp"] == 26 and e["played"]]
    if cup:
        e = max(cup, key=lambda x: (x["year"], x["mon"], x["day"], x["id"]))
        w, how = tie_winner(p, model, e)
        snap["cup"] = {"home": e["home"], "away": e["away"], "winner": w, "how": how,
                       "date": "%02d.%02d.%d" % (e["day"], e["mon"], e["year"])}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "season_snap.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print("в играта е", snap["date"])
    for reg, name in ((153, "шампионска група"), (154, "група за Европа"), (152, "редовен сезон"), (81, "втора лига")):
        t = snap["t%d" % reg]
        print("%s (%d): %s" % (name, reg, ", ".join("%d.%s (%dт/%dм)" % (i + 1, nm(c), pt, pl) for i, (c, pt, pl) in enumerate(t))))
    for reg, t in ties.items():
        print("бараж %d: %s - %s  %s  -> победител %s" % (reg, nm(t["home"]), nm(t["away"]), t["how"], nm(t["winner"])))
    if "cup" in snap:
        c = snap["cup"]
        print("купа 26, последен мач %s: %s - %s  %s  -> носител %s" % (c["date"], nm(c["home"]), nm(c["away"]), c["how"], nm(c["winner"])))
    print("запазено в %s" % out)


def cmd_verify(p, model):
    """след 01.07: сравнява новия сезон със снимката -- изпадане, промоция, суперкупа, Европа"""
    import json, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "season_snap.json")
    snap = json.load(open(path, encoding="utf-8"))
    print("в играта е", E.today(p, model), " снимка от", snap["date"])
    old1, old2 = set(snap["p20"]), set(snap["p81"])
    new1 = set(x >> 14 for x in (E.participants(p, model, 20) or []))
    new2 = set(x >> 14 for x in (E.participants(p, model, 81) or []))
    down, up = sorted(old1 - new1), sorted(new1 - old1)
    print("първа лига: %d отбора (преди %d)" % (len(new1), len(old1)))
    print("  изпаднали от първа: %s" % (", ".join(nm(c) for c in down) or "няма"))
    print("  качени в първа:     %s" % (", ".join(nm(c) for c in up) or "няма"))
    print("  изпадналите сега във втора: %s" % ("да" if set(down) <= new2 else "НЕ -- %s" % ", ".join(nm(c) for c in sorted(set(down) - new2))))
    print("  качените бяха във втора:    %s" % ("да" if set(up) <= old2 else "НЕ -- %s" % ", ".join(nm(c) for c in sorted(set(up) - old2))))
    t152 = [c for c, _, _ in snap["t152"]]
    t81 = [c for c, _, _ in snap["t81"]]
    ties = {int(k): v for k, v in snap["ties"].items()}
    in_ties = set()
    for reg in (170, 173):
        t = ties.get(reg)
        if t:
            in_ties.update((t["home"], t["away"]))
    rest1 = [c for c in t152 if c not in in_ties]
    rest2 = [c for c in t81 if c not in in_ties]
    exp_down = rest1[-1:]
    exp_up = rest2[:1]
    for reg in (170, 173):
        t = ties.get(reg)
        if not t or not t["winner"]:
            print("  бараж %d: няма резултат в снимката" % reg)
            continue
        loser = t["away"] if t["winner"] == t["home"] else t["home"]
        if t["winner"] in old2:
            exp_up.append(t["winner"]); exp_down.append(loser)
    print("  по правилника: изпадат %s; качват се %s" % (", ".join(nm(c) for c in sorted(exp_down)), ", ".join(nm(c) for c in sorted(exp_up))))
    print("  -> %s" % ("ВЯРНО" if sorted(exp_down) == down and sorted(exp_up) == up else "РАЗЛИКА"))
    t153 = [c for c, _, _ in snap["t153"]]
    cupw = snap.get("cup", {}).get("winner")
    if t153:
        champ = t153[0]
        opp = cupw if cupw and cupw != champ else (t153[1] if len(t153) > 1 else None)
        sc = [x >> 14 for x in (E.participants(p, model, 88) or [])]
        print("суперкупа 88: очаквано %s срещу %s, в играта %s -> %s" % (nm(champ), nm(opp), ", ".join(nm(c) for c in sc),
              "ВЯРНО" if set(sc) == {champ, opp} else "РАЗЛИКА"))
        where = {}
        for cid, name in PHASES:
            for i, raw in enumerate(E.participants(p, model, cid) or []):
                where.setdefault(raw >> E.TEAM_SHIFT, []).append("%s (%d.)" % (name, i + 1))
        print("Европа (шампион %s, втори %s, трети %s, купа %s, бараж 171 %s):" % (
            nm(champ), nm(t153[1]) if len(t153) > 1 else "-", nm(t153[2]) if len(t153) > 2 else "-", nm(cupw),
            nm(ties.get(171, {}).get("winner"))))
        for c in sorted(set(t152) | set(t153)):
            if c in where:
                print("  %-20s %s" % (nm(c), ", ".join(where[c])))


def cmd_fixtures(p, model):
    """мачовете на един клуб между два дни от годината: fixtures 1694 181 250"""
    a = [int(x) for x in sys.argv[2:] if x.isdigit()]
    words = " ".join(x for x in sys.argv[2:] if not x.isdigit() and not x.startswith("-")).strip()
    if words:
        nm(0)
        low = words.lower()
        exact = [c for c, n in _NAMES.items() if n.lower() == low]
        part = [c for c, n in _NAMES.items() if low in n.lower()]
        found = exact or part
        if not found:
            raise SystemExit("няма отбор с име \"%s\" в map_teams.txt" % words)
        if len(found) > 1 and not exact:
            print("по \"%s\" има няколко отбора: %s -- взимам първия" % (words, ", ".join(_NAMES[c] for c in found[:8])))
        club = found[0]
        lo, hi = (a[0], a[1]) if len(a) >= 2 else (181, 250)
    else:
        club = a[0] if a else 1694
        lo, hi = (a[1], a[2]) if len(a) >= 3 else (181, 250)
    print("в играта е", E.today(p, model), " клуб", nm(club))
    ms = []
    for e in all_events(p, model):
        if club not in (e["home"], e["away"]) or not e["mon"]:
            continue
        dd = sum((31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[:e["mon"] - 1]) + e["day"] - 1
        if lo <= dd <= hi:
            ms.append((dd, e))
    blob = comp_block(p, model)
    names = {}
    for i in range(E.COMP_N):
        o = i * E.COMP_REC
        names[struct.unpack_from("<H", blob, o)[0]] = blob[o + 2:o + 0x40].split(b"\0")[0].decode("utf-8", "replace")
    for dd, e in sorted(ms, key=lambda x: (x[0], x[1]["id"])):
        print("  ден %3d  %02d.%02d.%d  рег %5d %-34s %s - %s  %s" % (
            dd, e["day"], e["mon"], e["year"], e["comp"], names.get(e["comp"], "?")[:34],
            nm(e["home"]), nm(e["away"]), score_of(p, model, e) if e["played"] else ""))


def cmd_rebuild(p, model):
    """класирането на лига, сметнато наново от мачовете, ден по ден: rebuild 81"""
    a = [int(x) for x in sys.argv[2:] if x.isdigit()]
    reg = a[0] if a else 81
    print("в играта е", E.today(p, model), " лига", reg)
    raw = p.read(model + E.EVENT_OFF, E.EVENT_N * E.EVENT_REC)
    ms = []
    for e in all_events(p, model):
        if e["comp"] != reg or not e["played"] or not e["mon"]:
            continue
        o = e["id"] * E.EVENT_REC
        dd = sum((31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[:e["mon"] - 1]) + e["day"] - 1
        season = e["year"] if dd >= 181 else e["year"] - 1
        ms.append((season, e["year"], dd, e["home"], e["away"], raw[o + 0x1C], raw[o + 0x1F]))
    if not ms:
        print("няма изиграни мачове")
        return
    cur = max(m[0] for m in ms)
    ms = sorted([m for m in ms if m[0] == cur], key=lambda m: (m[1], m[2]))
    days = sorted(set((m[1], m[2]) for m in ms))
    print("сезон %d/%d: %d изиграни мача, последен ден %02d.%d" % (cur, cur + 1, len(ms), days[-1][1], days[-1][0]))

    def table(upto):
        t = defaultdict(lambda: [0, 0, 0, 0])
        for s, y, dd, h, aw, hg, ag in ms:
            if (y, dd) > upto:
                continue
            for c, f, g in ((h, hg, ag), (aw, ag, hg)):
                r = t[c]
                r[0] += 3 if f > g else 1 if f == g else 0
                r[1] += f - g
                r[2] += f
                r[3] += 1
        return sorted(t.items(), key=lambda kv: (-kv[1][0], -kv[1][1], -kv[1][2]))

    for upto in days[-3:]:
        t = table(upto)
        print("след %d-ти ден от годината (%d):" % (upto[1], upto[0]))
        for i, (c, r) in enumerate(t[:5]):
            print("  %2d. %-18s %3dт  гр.разл. %+d  %dм" % (i + 1, nm(c), r[0], r[1], r[3]))
    game = {c: (pt, pl) for c, pt, pl in newest_table(p, reg)}
    mine = dict(table(days[-1]))
    bad = []
    print("сравнение с класирането в играта (точки / мачове):")
    for c, r in sorted(mine.items(), key=lambda kv: -kv[1][0]):
        g = game.get(c, (None, None))
        mark = "" if g == (r[0], r[3]) else "   <-- РАЗЛИКА"
        if mark:
            bad.append(c)
        print("  %-18s по резултатите %3dт %2dм   в играта %s%s" % (nm(c), r[0], r[3],
              "%dт %dм" % g if g[0] is not None else "няма", mark))
    for c in bad:
        print("мачовете на %s:" % nm(c))
        for s_, y, dd, h, aw, hg, ag in ms:
            if c in (h, aw):
                print("  %02d.%d  %s - %s  %d:%d" % (dd, y, nm(h), nm(aw), hg, ag))
    evs = [e for e in all_events(p, model) if e["comp"] == reg and e["played"] and set(bad) & {e["home"], e["away"]}]
    for e in evs:
        o = e["id"] * E.EVENT_REC
        extra = raw[o + 0x1C:o + 0x22]
        if extra[1] or extra[2] or extra[4] or extra[5]:
            print("  особен мач %s - %s: полета %s" % (nm(e["home"]), nm(e["away"]), extra.hex(" ")))
    last = [m for m in ms if (m[1], m[2]) == days[-1]]
    print("последният кръг:")
    for s, y, dd, h, aw, hg, ag in last:
        print("  %s - %s  %d:%d" % (nm(h), nm(aw), hg, ag))
    for pr in (170, 173):
        pp = [x >> 14 for x in (E.participants(p, model, pr) or [])]
        print("бараж %d в паметта: %s" % (pr, " - ".join(nm(c) for c in pp) or "празен"))


def cmd_rowfix(p, model):
    """точките вървят с отбора след размяната на местата: rowfix 81 (показва), rowfix 81 --apply"""
    a = [int(x) for x in sys.argv[2:] if x.isdigit()]
    reg = a[0] if a else 81
    apply = "--apply" in sys.argv
    print("в играта е", E.today(p, model), " лига", reg)
    raw = p.read(model + E.EVENT_OFF, E.EVENT_N * E.EVENT_REC)
    ms = []
    for e in all_events(p, model):
        if e["comp"] != reg or not e["played"] or not e["mon"]:
            continue
        o = e["id"] * E.EVENT_REC
        dd = sum((31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[:e["mon"] - 1]) + e["day"] - 1
        ms.append((e["year"] if dd >= 181 else e["year"] - 1, e["home"], e["away"], raw[o + 0x1C], raw[o + 0x1F]))
    cur = max(m[0] for m in ms)
    pts, pl = defaultdict(int), defaultdict(int)
    for s_, h, aw, hg, ag in ms:
        if s_ != cur:
            continue
        for c, f, g in ((h, hg, ag), (aw, ag, hg)):
            pts[c] += 3 if f > g else 1 if f == g else 0
            pl[c] += 1
    S = struct.unpack("<Q", p.read(E.root_of(p, BASE[0]) + E.STAND_OFF, 8))[0]
    best, addr = -1, None
    for i in range(E.STAND_N):
        at = S + E.STAND_BASE + i * E.STAND_REC
        hd = p.read(at, 4)
        if struct.unpack_from("<H", hd, 0)[0] == reg and struct.unpack_from("<H", hd, 2)[0] > best:
            best, addr = struct.unpack_from("<H", hd, 2)[0], at
    rec = p.read(addr, E.STAND_REC)
    n = struct.unpack_from("<I", rec, E.ST_COUNT)[0]
    print("запис %x, година %d, %d отбора" % (addr, best, n))

    def rows(off, stride):
        return [bytearray(rec[off + k * stride: off + (k + 1) * stride]) for k in range(n)]

    main, prev, order = rows(E.ST_ROWS, 20), rows(E.ST_PREV, 20), rows(E.ST_ORDER, 16)
    for k in range(min(n, 5)):
        c = struct.unpack_from("<I", main[k], 0)[0] >> 14
        print("  %d. %-16s ред %s | преден %s | ред2 %s" % (k + 1, nm(c), main[k].hex(" "), prev[k].hex(" "), order[k].hex(" ")))
    bad = [k for k in range(n) if main[k][8] != pts[struct.unpack_from("<I", main[k], 0)[0] >> 14]]
    if not bad:
        print("точките на всеки ред са на неговия отбор -- няма какво да се прави")
        return
    fix = {}
    for k in bad:
        c = struct.unpack_from("<I", main[k], 0)[0] >> 14
        src = [j for j in bad if main[j][8] == pts[c] and main[j][0x0F] == pl[c] and j not in fix.values()]
        if not src:
            print("не намирам точките на %s (%d) в разменените редове -- спирам" % (nm(c), pts[c]))
            return
        fix[k] = src[0]
    for k, j in sorted(fix.items()):
        c = struct.unpack_from("<I", main[k], 0)[0] >> 14
        print("  място %d %s: точки %d -> %d (данните от ред %d)" % (k + 1, nm(c), main[k][8], main[j][8], j + 1))
    same_prev = all(prev[k][:4] == main[k][:4] for k in fix)
    print("класирането от предния кръг е със същите отбори на тези места: %s" % ("да -- поправя се и то" if same_prev else "не -- не го пипам"))
    if not apply:
        print("само показано. За да се запише: rowfix %d --apply" % reg)
        return
    newm = {k: main[k][:8] + main[j][8:] for k, j in fix.items()}
    newp = {k: prev[k][:8] + prev[j][8:] for k, j in fix.items()} if same_prev else {}
    for k, b in newm.items():
        p.write(addr + E.ST_ROWS + k * 20, bytes(b))
    for k, b in newp.items():
        p.write(addr + E.ST_PREV + k * 20, bytes(b))
    print("записано: %d реда%s" % (len(newm), " и в предното класиране" if newp else ""))


def cmd_entrants(p, model):
    """кой е записан в европейските турнири сега: entrants (2, 3, 5, 188 и двойките на 188)"""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    regs = [int(a) for a in sys.argv[2:] if a.isdigit()] or [2, 3, 5, 188] + [188 + 1024 * k for k in range(1, 9)] + [2 + 1024 * k for k in range(1, 9)]
    print("в играта е", E.today(p, model))
    at = {}
    for i in range(min(n, E.COMP_N)):
        at[struct.unpack_from("<H", blob, i * E.COMP_REC)[0]] = i * E.COMP_REC
    for cid in regs:
        if cid not in at:
            print("%5d: няма запис" % cid)
            continue
        o = at[cid]
        w300 = struct.unpack_from("<I", blob, o + 0x300)[0]
        cnt = struct.unpack_from("<H", blob, o + 0x30A)[0] & 0x7F
        yr = struct.unpack_from("<H", blob, o + 0x2FC)[0]
        started = blob[o + 0x305] & 1
        rounds = (w300 >> 19) & 0x3F
        cl = [struct.unpack_from("<I", blob, o + 0x170 + 4 * k)[0] >> 14 for k in range(cnt)]
        print("%5d: година %d, пуснат %d, кръгове %d, отбори %d, +76=%04x +80=%04x +84=%04x" % (
            cid, yr, started, rounds, cnt, struct.unpack_from("<H", blob, o + 0x76)[0],
            struct.unpack_from("<H", blob, o + 0x80)[0], struct.unpack_from("<H", blob, o + 0x84)[0]))
        for k in range(0, len(cl), 6):
            print("        " + ", ".join("%d.%s" % (k + j + 1, nm(c)) for j, c in enumerate(cl[k:k + 6])))


def cmd_countries(p, model):
    """държавата на всеки клуб от лиговите фази и мачовете между отбори от една държава"""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    print("в играта е", E.today(p, model))
    recs = []
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        cid = struct.unpack_from("<H", blob, o)[0]
        if cid in (0, 0xFFFF):
            continue
        cnt = struct.unpack_from("<H", blob, o + 0x30A)[0] & 0x7F
        f308 = struct.unpack_from("<I", blob, o + 0x308)[0]
        f30c = struct.unpack_from("<I", blob, o + 0x30C)[0]
        cl = set(struct.unpack_from("<I", blob, o + 0x170 + 4 * k)[0] >> 14 for k in range(min(cnt, 100)))
        recs.append((cid, (f308 >> 23) & 0x3F, (f30c >> 7) & 0x3F, cnt, cl))
    euro = lambda c: (c & 0x3FF) in (2, 3, 4, 5, 6, 7, 188) or c in (1027, 1029)
    where = {}
    for cid, fmt, ctry, cnt, cl in recs:
        if euro(cid):
            continue
        for c in cl:
            where.setdefault(c, []).append((cid, fmt, ctry, cnt))
    country = {}
    for ph in (1027, 1029):
        cl = [x >> 14 for x in (E.participants(p, model, ph) or [])]
        print("%d: %d клуба" % (ph, len(cl)))
        for c in cl:
            w = sorted(where.get(c, []))
            lg = [x for x in w if x[3] >= 10]
            country[c] = lg[0][2] if lg else None
            print("   %-22s държава %-4s в: %s" % (nm(c), country[c], " ".join("%d(вид %d, държ %d, %d отб)" % x for x in w) or "никъде"))
    ev = all_events(p, model)
    for ph in (1027, 1029):
        same = [e for e in ev if e["comp"] == ph and country.get(e["home"]) is not None and country.get(e["home"]) == country.get(e["away"])]
        print("%d: мачове между отбори от една държава: %d" % (ph, len(same)))
        for e in same:
            print("   %02d.%02d  %s - %s  (държава %s)" % (e["day"], e["mon"], nm(e["home"]), nm(e["away"]), country[e["home"]]))


def score_of(p, model, e):
    """резултатът на изигран мач: голове, и ако има - продължения и дузпи"""
    r = p.read(model + E.EVENT_OFF + e["id"] * E.EVENT_REC, 0x24)
    out = "%d:%d" % (r[0x1C], r[0x1F])
    if r[0x1D] or r[0x20]:
        out += " (след продължения %d:%d)" % (r[0x1D], r[0x20])
    if r[0x1E] or r[0x21]:
        out += " (дузпи %d:%d)" % (r[0x1E], r[0x21])
    return out


def cmd_uclpo(p, model):
    """августовският плейоф за ШЛ: двойките, резултатите, кой продължава и къде е всеки отбор сега"""
    print("в играта е", E.today(p, model))
    ev = [e for e in all_events(p, model) if (e["comp"] & 0x3FF) == 2 and e["comp"] > 1024 and e["mon"] in (8, 9)]
    if not ev:
        print("няма мачове от августовския плейоф на ШЛ в паметта (преди 1 август или след февруари)")
        return
    ucl = set(x >> 14 for x in (E.participants(p, model, 1027) or []))
    uel = set(x >> 14 for x in (E.participants(p, model, 1029) or []))
    bg = set(x >> 14 for x in (E.participants(p, model, 20) or []))

    def now(c):
        return "ШЛ" if c in ucl else "ЛЕ" if c in uel else "никъде (още няма жребий или е отпаднал)"

    ties = defaultdict(list)
    for e in ev:
        ties[e["comp"]].append(e)
    nbg = 0
    for cid in sorted(ties):
        legs = sorted(ties[cid], key=lambda x: (x["mon"], x["day"], x["id"]))
        a, b = legs[0]["home"], legs[0]["away"]
        ga = gb = 0
        mark = "  <-- БЪЛГАРСКИ ОТБОР" if (a in bg or b in bg) else ""
        nbg += bool(mark)
        print("двойка %d: %s - %s%s" % (cid, nm(a), nm(b), mark))
        allp = True
        for e in legs:
            if not e["played"]:
                allp = False
                print("    %02d.%02d  %s - %s  неизигран" % (e["day"], e["mon"], nm(e["home"]), nm(e["away"])))
                continue
            r = p.read(model + E.EVENT_OFF + e["id"] * E.EVENT_REC, 0x24)
            if e["home"] == a:
                ga += r[0x1C]; gb += r[0x1F]
            else:
                ga += r[0x1F]; gb += r[0x1C]
            print("    %02d.%02d  %s - %s  %s" % (e["day"], e["mon"], nm(e["home"]), nm(e["away"]), score_of(p, model, e)))
        if allp:
            print("    общо %s %d:%d %s" % (nm(a), ga, gb, nm(b)))
        print("    сега: %s -> %s;  %s -> %s" % (nm(a), now(a), nm(b), now(b)))
    print("български отбори в плейофа: %d" % nbg)
    print("български отбори в лиговата фаза на ШЛ: %s" % (", ".join(nm(c) for c in sorted(ucl & bg)) or "няма"))
    print("български отбори в лиговата фаза на ЛЕ: %s" % (", ".join(nm(c) for c in sorted(uel & bg)) or "няма"))


def club_index_map(p, model):
    """{индекс на клубния запис: номер на клуба} от участниците на всички състезания"""
    blob = comp_block(p, model)
    n = struct.unpack("<I", p.read(model + 0xD0BCF4, 4))[0]
    out = {}
    for i in range(min(n, E.COMP_N)):
        o = i * E.COMP_REC
        cnt = struct.unpack_from("<H", blob, o + 0x30A)[0] & 0x7F
        for k in range(min(cnt, 100)):
            raw = struct.unpack_from("<I", blob, o + 0x170 + 4 * k)[0]
            if raw >> 14 not in (0, 0x3FFFF):
                out[raw & 0x3FFF] = raw >> 14
    return out


def cmd_rankfind(p, model):
    """търси в клубните записи поле, което прилича на ранглиста (всеки клуб с различно място)"""
    print("в играта е", E.today(p, model))
    idx = club_index_map(p, model)
    nclub = struct.unpack("<I", p.read(model + 0xD0BCEC, 4))[0]
    nclub = min(nclub, 0x2EE)
    REC = 0x690
    blob = p.read(model + 0xADF4BC, nclub * REC)
    known = sorted(i for i in idx if i < nclub)
    print("клубни записи: %d, от тях с известен клуб: %d" % (nclub, len(known)))
    found = 0
    for width, fmt in ((2, "<H"), (4, "<I")):
        for off in range(0, REC - width + 1):
            vals = [struct.unpack_from(fmt, blob, i * REC + off)[0] for i in known]
            if len(set(vals)) != len(vals):
                continue
            lo, hi = min(vals), max(vals)
            if hi - lo > 4 * len(vals) or hi > 5000:
                continue
            order = sorted(zip(vals, known))
            found += 1
            print("поле +0x%03X (%d байта): стойности %d..%d, всички различни" % (off, width, lo, hi))
            print("    най-малките: " + ", ".join("%d %s" % (v, nm(idx[i])) for v, i in order[:12]))
            print("    най-големите: " + ", ".join("%d %s" % (v, nm(idx[i])) for v, i in order[-6:]))
    if not found:
        print("няма такова поле в клубните записи -- ранглистата се пази другаде")
    names = ["Manchester City", "Real Madrid", "Bayern", "Chelsea", "Juventus", "Borussia Dortmund", "PSV", "Fenerbahce", "Aberdeen", "Levski", "Ludogorets", "Vihren"]
    nm(0)
    pick = []
    for w in names:
        for c, n_ in _NAMES.items():
            if w.lower() in n_.lower():
                r = [i for i, cc in idx.items() if cc == c and i < nclub]
                if r:
                    pick.append((n_, r[0]))
                break
    out = os_path_join_here("club_records.txt")
    with open(out, "w", encoding="utf-8") as f:
        for n_, i in pick:
            f.write("%s (запис %d)\n" % (n_, i))
            rec = blob[i * REC:(i + 1) * REC]
            for k in range(0, REC, 32):
                f.write("  %03x: %s\n" % (k, rec[k:k + 32].hex(" ")))
    print("суровите записи на %d клуба са записани в %s" % (len(pick), out))


def os_path_join_here(name):
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def cmd_rankseek(p, model):
    """търси в паметта списък, в който първите пет отбора от ранглистата стоят един след друг"""
    import time
    t0 = time.time()
    print("в играта е", E.today(p, model))
    top = [109, 114, 173, 127, 108]          # Real Madrid, PSG, Manchester City, Bayern, Barcelona
    print("търся подред: %s" % ", ".join(nm(c) for c in top))
    real_raw = struct.pack("<I", (109 << 14) | 54)
    hits = []

    def check(buf, pos, stride, enc):
        for k in range(1, 5):
            q = pos + stride * k
            if q + 4 > len(buf):
                return False
            if enc == "raw":
                v = struct.unpack_from("<I", buf, q)[0] >> 14
            elif enc == "u32":
                v = struct.unpack_from("<I", buf, q)[0]
            else:
                v = struct.unpack_from("<H", buf, q)[0]
            if v != top[k]:
                return False
        return True

    def show(base, buf, pos, stride, enc):
        where = "model+0x%X" % (base + pos - model) if 0 <= base + pos - model < 0x2000000 else "извън model"
        print("НАМЕРЕНО на %X (%s), стъпка %d байта, вид %s" % (base + pos, where, stride, enc))
        names = []
        for k in range(0, 40):
            q = pos + stride * k
            if q + 4 > len(buf):
                break
            v = struct.unpack_from("<I", buf, q)[0]
            c = v >> 14 if enc == "raw" else v if enc == "u32" else v & 0xFFFF
            names.append("%d.%s" % (k + 1, nm(c)))
        for k in range(0, len(names), 8):
            print("    " + ", ".join(names[k:k + 8]))
        for k in range(0, 3):
            q = pos + stride * k
            print("    запис %d: %s" % (k + 1, buf[q:q + stride].hex(" ")))
        back = buf[max(0, pos - 32):pos]
        print("    32 байта преди: %s" % back.hex(" "))

    total = 0
    CH = 0x1000000
    for base, size in E.mem_regions(p):
        inmodel = base <= model + 0x1A00000 and base + size > model
        for off in range(0, size, CH):
            n = min(CH + 0x400, size - off)
            buf = p.read(base + off, n)
            if not buf:
                continue
            total += len(buf)
            pos = buf.find(real_raw)
            while pos >= 0:
                for stride in range(4, 0x101, 2):
                    if check(buf, pos, stride, "raw"):
                        hits.append(1)
                        show(base + off, buf, pos, stride, "raw")
                pos = buf.find(real_raw, pos + 1)
            if inmodel:
                for enc, needle in (("u32", struct.pack("<I", 109)), ("u16", struct.pack("<H", 109))):
                    pos = buf.find(needle)
                    while pos >= 0:
                        for stride in range(2 if enc == "u16" else 4, 0x81, 2):
                            if check(buf, pos, stride, enc):
                                hits.append(1)
                                show(base + off, buf, pos, stride, enc)
                        pos = buf.find(needle, pos + 1)
    print("прегледани %d MB за %d сек; намерени списъци: %d" % (total >> 20, time.time() - t0, len(hits)))


RANK_OFF, RANK_REC, RANK_MAX = 0x16705A8, 16, 800


def rank_table(p, model):
    """ранглистата на клубовете: {клуб: (място, точки)} от model+0x16705A8 (записи по 16 байта)"""
    blob = p.read(model + RANK_OFF, RANK_REC * RANK_MAX)
    out = {}
    for k in range(RANK_MAX):
        raw, rank = struct.unpack_from("<II", blob, k * RANK_REC)
        pts = struct.unpack_from("<H", blob, k * RANK_REC + 8)[0]
        if rank != k + 1 or raw >> 14 in (0, 0x3FFFF):
            break
        out[raw >> 14] = (rank, pts)
    return out


def cmd_ranks(p, model):
    """ранглистата: колко отбора има, местата на българските и на отборите в плейофа за ШЛ"""
    print("в играта е", E.today(p, model))
    rt = rank_table(p, model)
    print("отбори в ранглистата: %d" % len(rt))
    top = sorted(rt.items(), key=lambda kv: kv[1][0])
    print("първите 10: " + ", ".join("%d.%s (%d т.)" % (r, nm(c), pt) for c, (r, pt) in top[:10]))
    bg = [x >> 14 for x in (E.participants(p, model, 20) or [])]
    print("първа лига:")
    for c in sorted(bg, key=lambda c: rt.get(c, (9999, 0))[0]):
        print("   %-18s %s" % (nm(c), "място %d (%d т.)" % rt[c] if c in rt else "няма го в ранглистата"))
    po = [x >> 14 for x in (E.participants(p, model, 2) or [])]
    if po:
        print("плейоф за ШЛ (%d отбора), подредени по ранглистата:" % len(po))
        order = sorted(po, key=lambda c: rt.get(c, (9999, 0))[0])
        for i, c in enumerate(order):
            print("   %2d. %-26s %s%s" % (i + 1, nm(c), "място %d (%d т.)" % rt[c] if c in rt else "няма го в ранглистата",
                  "   <- слабата половина" if i >= len(order) // 2 else ""))
    else:
        print("в плейофа за ШЛ още няма отбори")


def cmd_table(p, model):
    """класирането, както го пази играта за дадени регулации: table 20 152"""
    regs = [int(a) for a in sys.argv[2:] if a.isdigit()] or [20, 152]
    print("в играта е", E.today(p, model))
    for reg in regs:
        t = newest_table(p, reg)
        print("рег %d: %d реда" % (reg, len(t)))
        for i, (c, pt, pl) in enumerate(t):
            print("   %2d. %-20s %3d т.  %2d мача" % (i + 1, nm(c), pt, pl))


def cmd_uelwin(p, model):
    """носителят на ЛЕ директно в ШЛ: показва редовете на таблицата за класиране; с --apply ги сменя
    само в паметта (до затваряне на играта): плейоф за ШЛ (1) -> лигова фаза на ШЛ (0)"""
    base = BASE[0]
    apply = "--apply" in sys.argv
    print("в играта е", E.today(p, model))
    rows = ((0x34F1FA0, (1, 133)), (0x34EECC0, (1, 113)))
    ok = True
    for tab, idxs in rows:
        for i in idxs:
            at = base + tab + 12 * i
            reg, pad, pos, stage = struct.unpack("<HHII", p.read(at, 12))
            what = {0: "лигова фаза на ШЛ", 1: "плейоф за ШЛ", 2: "ЛЕ"}.get(stage, "?")
            print("таблица %X ред %3d: рег %d място %d -> етап %d (%s)" % (tab, i, reg, pos, stage, what))
            if reg != 6 or pos != 0 or stage not in (0, 1):
                ok = False
    if not ok:
        print("редовете не са очакваните (носителят на ЛЕ) -- нищо не пиша")
        return
    if not apply:
        print("само показано. За смяна до затварянето на играта: uelwin --apply")
        return
    for tab, idxs in rows:
        for i in idxs:
            p.write(base + tab + 12 * i + 8, struct.pack("<I", 0))
    print("записано: носителят на ЛЕ влиза директно в лиговата фаза на ШЛ (до затваряне на играта)")


def cmd_eurows(p, model):
    """редовете за Европа, както DLL-ът ги е подредил днес: носителите (0, 1) и българските (16-21)"""
    base = BASE[0]
    print("в играта е", E.today(p, model))
    t20 = newest_table(p, 20)
    stage = {0: "ШЛ лигова фаза", 1: "ШЛ плейоф", 2: "ЛЕ", 7: "(изключен)", 11: "бараж 171"}
    for i in (0, 1, 16, 17, 18, 19, 20, 21):
        reg, pad, pos, st = struct.unpack("<HHII", p.read(base + 0x34F1FA0 + 12 * i, 12))
        who = ""
        if reg == 20 and 13 <= pos < 13 + len(t20):
            who = "%d. в първа лига: %s" % (pos - 12, nm(t20[pos - 13][0]))
        elif reg in (4, 6, 26, 171) and pos == 0:
            who = {4: "носител на ШЛ", 6: "носител на ЛЕ", 26: "носител на Купата на България", 171: "победител в баража за Европа"}[reg]
        else:
            who = "рег %d място %d" % (reg, pos)
        print("ред %3d: %-38s -> %s" % (i, who, stage.get(st, "етап %d" % st)))


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main():
    import os
    name = sys.argv[1] if len(sys.argv) > 1 else "state"
    extra = "_".join(a for a in sys.argv[2:] if a.isdigit())
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "probe_%s%s.txt" % (name.lstrip("-"), ("_" + extra) if extra else ""))
    fh = open(out, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, fh)
    try:
        _main()
    finally:
        sys.stdout = sys.stdout.streams[0]
        fh.close()
        print("(записано и в %s)" % out)


def _main():
    p, base, model = attach()
    BASE[0] = base
    cmd = sys.argv[1] if len(sys.argv) > 1 else "state"
    {"state": cmd_state, "dups": cmd_dups, "days": cmd_days, "ko": cmd_ko, "diary": cmd_diary, "agenda": cmd_agenda, "diaryfix": cmd_diaryfix, "bg": cmd_bg, "tables": cmd_tables, "selfcarry": cmd_selfcarry, "super": cmd_super, "fields": cmd_fields, "slots": cmd_slots, "slotfix": cmd_slotfix, "extras": cmd_extras, "grpday": cmd_grpday, "order": cmd_order, "rounds": cmd_rounds, "comp": cmd_comp, "events": cmd_events, "stalefix": cmd_stalefix, "health": cmd_health, "snap": cmd_snap, "verify": cmd_verify, "fixtures": cmd_fixtures, "rebuild": cmd_rebuild, "rowfix": cmd_rowfix, "entrants": cmd_entrants, "countries": cmd_countries, "uclpo": cmd_uclpo, "rankfind": cmd_rankfind, "rankseek": cmd_rankseek, "ranks": cmd_ranks, "table": cmd_table, "uelwin": cmd_uelwin, "eurows": cmd_eurows}.get(cmd, cmd_state)(p, model)


if __name__ == "__main__":
    main()
