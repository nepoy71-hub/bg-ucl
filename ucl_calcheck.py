# ucl_calcheck.py  -  календарите в PES2021.exe и дублиращите се дати с UCL/UEL
#
# Чете exe-то и CompetitionRegulation.bin от диска. Играта не се пуска и нищо не се пише.
#
# Как играта дава дати: 0x14157F810 е switch по id на регулацията. Байтовата
# таблица на 0x1415802E8 дава за id 1..175 номер на случай, таблицата на
# 0x1415801EC дава входа на случая. Всеки случай вика малък строител, който
# копира статичен масив от записи по 12 байта: u32 ден от годината
# (1 януари = 0), u32 кръг, u32 вид.
#
# Отгоре се прилагат кръпките на bg_link 2.31, които живеят само в паметта:
#   байтовете на 170/171/173 -> случай 55
#   152 (редовен сезон) -> таблица 0x298F490, 30 записа; кръг 24: 44->51, кръг 25: 51->58
#   153/154 (групи)     -> таблица 0x298F600, 7 записа;  кръг 0: 86->79
#
# Изход:
#   1. датите на всяко състезание от твоите данни
#   2. всеки ден на UCL/UEL (оригиналните на Konami и предложените от fl26swiss)
#      и кои национални състезания играят същия ден
#   3. свободните дни (без нито едно национално първенство/купа) от август до май
#
# Нужно: pip install capstone
# Пускане:
#   python ucl_calcheck.py "C:\Games\eFootball PES 2021\PES2021.exe" "C:\Games\eFootball PES 2021\sider-7.4.1\livecpk\yopen\common\etc\pesdb\CompetitionRegulation.bin"

import struct
import sys
import zlib
import datetime

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_REG

IMG = 0x140000000
SWITCH_TABLE = 0x1415801EC
CASE_BYTES = 0x1415802E8
NCASES, LAST_ID, CASE_EMPTY = 63, 175, 62
REC = 0x930

BG_CASE = {170: 55, 171: 55, 173: 55}
BG_TABLES = {
    152: (0x14298F490, 30, {24: 51, 25: 58}),
    153: (0x14298F600, 7, {0: 79}),
    154: (0x14298F600, 7, {0: 79}),
}

# id на регулациите, които са европейски (оригинални на Konami)
EURO = {2: "UCL плейоф (авг.)", 3: "UCL групи", 4: "UCL елиминации",
        5: "UEL групи", 6: "UEL елиминации", 7: "Суперкупа на UEFA"}

# fl26swiss: 16 дни на лиговата фаза; UEL е +2 дни; плейоф 9-24 и елиминации
SWISS_UCL = [259, 260, 273, 274, 294, 295, 308, 309, 329, 330, 343, 344, 20, 21, 28, 29]
SWISS_UEL = [d + 2 for d in SWISS_UCL]
SWISS_KO = {"UCL плейоф 9-24": [47, 54], "UCL 1/8": [68, 75], "UCL 1/4": [96, 103],
            "UCL 1/2": [117, 124], "UCL финал": [149],
            "UEL плейоф 9-24": [47, 54], "UEL 1/8": [70, 77], "UEL 1/4": [98, 105],
            "UEL 1/2": [119, 126], "UEL финал": [139]}


def dstr(d):
    return (datetime.date(2025, 1, 1) + datetime.timedelta(days=d)).strftime("%d.%m")


class Image:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opt = struct.unpack_from("<H", d, pe + 20)[0]
        self.secs = []
        for i in range(nsec):
            p = pe + 24 + opt + i * 40
            vs, va, rs, rp = struct.unpack_from("<IIII", d, p + 8)
            self.secs.append((va, max(vs, rs), rp, rs))
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True

    def off(self, va):
        r = va - IMG
        for vaS, vs, rp, rs in self.secs:
            if vaS <= r < vaS + vs:
                k = r - vaS
                return rp + k if k < rs else None
        return None

    def u32(self, va):
        return struct.unpack_from("<I", self.data, self.off(va))[0]

    def code(self, va, n=200):
        o = self.off(va)
        return self.data[o:o + n]

    def days(self, arr, cnt):
        o = self.off(arr)
        if o is None:
            return None
        return [struct.unpack_from("<I", self.data, o + i * 12)[0] for i in range(cnt)]


def follow(img, va):
    for ins in img.md.disasm(img.code(va), va):
        if ins.mnemonic in ("jmp", "call") and ins.op_str.startswith("0x"):
            return int(ins.op_str, 16)
        if ins.mnemonic == "ret":
            return None
    return None


def builder(img, va):
    arr = cnt = None
    for ins in img.md.disasm(img.code(va), va):
        if arr is None and ins.mnemonic == "lea" and "rip" in ins.op_str:
            arr = ins.address + ins.size + ins.operands[1].mem.disp
        elif arr is not None and cnt is None and ins.mnemonic == "mov" \
                and len(ins.operands) == 2 and ins.operands[0].type == X86_OP_REG \
                and ins.operands[1].type == X86_OP_IMM and 0 < ins.operands[1].imm < 0x100:
            cnt = ins.operands[1].imm
        if arr is not None and cnt is not None:
            return arr, cnt
        if ins.mnemonic == "ret":
            break
    return arr, cnt


def cases(img):
    out = {}
    for c in range(NCASES):
        entry = img.u32(SWITCH_TABLE + c * 4) + IMG
        b = follow(img, entry)
        if b is None:
            continue
        arr, cnt = builder(img, b)
        if not arr or not cnt:
            continue
        ds = img.days(arr, cnt)
        if not ds or any(x > 366 for x in ds):
            continue
        out[c] = ds
    return out


def regulations(path):
    raw = open(path, "rb").read()
    if raw[3:8] == b"WESYS":
        csz = struct.unpack_from("<I", raw, 8)[0]
        raw = zlib.decompress(raw[16:16 + csz])
    out = {}
    for i in range(len(raw) // REC):
        r = raw[i * REC:(i + 1) * REC]
        rid = struct.unpack_from("<H", r, 2)[0]
        if rid > 0xFF:
            continue
        name = r[0x14:0x14 + 0x73].split(b"\0")[0].decode("utf-8", "replace")
        out.setdefault(rid, (r[8], r[9], r[0xB], name))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    exe = sys.argv[1] if len(sys.argv) > 1 else r"C:\Games\eFootball PES 2021\PES2021.exe"
    regp = sys.argv[2] if len(sys.argv) > 2 else \
        r"C:\Games\eFootball PES 2021\sider-7.4.1\livecpk\yopen\common\etc\pesdb\CompetitionRegulation.bin"
    img = Image(exe)
    cs = cases(img)
    o = img.off(CASE_BYTES)
    idc = {i: img.data[o + i - 1] for i in range(1, LAST_ID + 1)}
    idc.update(BG_CASE)
    regs = regulations(regp)

    cal, missing = {}, []
    for rid in sorted(regs):
        comp, typ, n, name = regs[rid]
        if rid in BG_TABLES:
            tab, cnt, fix = BG_TABLES[rid]
            ds = img.days(tab, cnt)
            if ds:
                ds = [fix.get(k, d) for k, d in enumerate(ds)]
        elif rid <= LAST_ID and idc.get(rid, CASE_EMPTY) in cs:
            ds = cs[idc[rid]]
        else:
            ds = None
        if ds:
            cal[rid] = ds
        else:
            missing.append(rid)

    print("=" * 78)
    print("1. ДАТИТЕ НА ВСЯКО СЪСТЕЗАНИЕ (ден от годината / дата)")
    print("=" * 78)
    for rid, ds in cal.items():
        comp, typ, n, name = regs[rid]
        print("рег %3d  случай %-3s тип %d  %2d отб.  %s" % (
            rid, "bg" if rid in BG_TABLES else idc.get(rid), typ, n, name[:40]))
        print("         " + " ".join("%d(%s)" % (d, dstr(d)) for d in ds))
    print("без дати в exe-то: " + ", ".join(str(r) for r in missing))

    dom = {rid: ds for rid, ds in cal.items() if rid not in EURO}
    byday = {}
    for rid, ds in dom.items():
        for d in ds:
            byday.setdefault(d, set()).add(rid)

    def clash(title, days):
        print("\n" + title)
        bad = 0
        for d in days:
            who = sorted(byday.get(d, ()))
            mark = "СВОБОДЕН" if not who else "ДУБЛИРА: " + ", ".join(
                "%d %s" % (r, regs[r][3][:22]) for r in who)
            if who:
                bad += 1
            print("  %3d %s  %s" % (d, dstr(d), mark))
        print("  -> %d от %d дни се дублират" % (bad, len(days)))

    print("\n" + "=" * 78)
    print("2. ЕВРОПЕЙСКИТЕ ДНИ СРЕЩУ НАЦИОНАЛНИТЕ КАЛЕНДАРИ")
    print("=" * 78)
    for rid in sorted(EURO):
        if rid in cal:
            clash("Konami рег %d - %s" % (rid, EURO[rid]), cal[rid])
    clash("fl26swiss - лигова фаза UCL", SWISS_UCL)
    clash("fl26swiss - лигова фаза UEL (+2 дни)", SWISS_UEL)
    for k, v in SWISS_KO.items():
        clash("fl26swiss - " + k, v)

    print("\n" + "=" * 78)
    print("3. СВОБОДНИ ДНИ (без национален мач), август - май")
    print("=" * 78)
    season = list(range(213, 365)) + list(range(0, 151))
    free = [d for d in season if d not in byday]
    for d in free:
        print("  %3d %s" % (d, dstr(d)))
    print("  -> %d свободни дни" % len(free))


if __name__ == "__main__":
    main()
