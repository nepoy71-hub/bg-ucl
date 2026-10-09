# ucl_sigcheck.py  -  проверка на PES2021.exe за мода UCL нов формат
#
# Чете exe-то от диска (не пипа играта, не пише нищо) и сравнява байтовете
# на всяко място, което DLL-ът за новия формат ще кръпва, с онова, което
# очаква сорсът на fl26swiss (Matozanato, build FL_2026.exe 26.0.0.0).
# Отделно показва кои от тези места се застъпват с кръпките на bg_link 2.31.
#
# Пускане:
#   python ucl_sigcheck.py "C:\Games\eFootball PES 2021\PES2021.exe"

import struct
import sys

BASE = 0x140000000

# (име, RVA, очаквани байтове, нужно ли е за UCL/UEL, какво е)
SITES = [
    ("GEN",      0x13F3E00, "48894c24085356574883ec60410fb6f8",       True,  "генератор на програмата (швейцарския жребий)"),
    ("DATE",     0x157F810, "40555357488bec4883ec20488bda0fb7f9",     True,  "датите на кръговете"),
    ("GROUP",    0x13F3C30, "48895c241855574156488d6c24b9",           True,  "строител на група от 4 (изключва се за 36)"),
    ("ADDCLUB",  0x14C9A10, "448b81080300004c8bc9418bc089542410",     True,  "добавя клуб в регулация"),
    ("CLRCLUB",  0x14C9740, "4c8bc9488d917001000041b830000000",       True,  "изчиства клубовете на регулация"),
    ("SETCOUNT", 0x14CA080, "81a108030000ffff80ff83e27fc1e210",       True,  "брой клубове"),
    ("SEED",     0x155CD30, "488bc455488d68a14881ecb0000000",         True,  "урните (празнеше списъка при 1 група от 36)"),
    ("GDRAW",    0x15485C0, "488bc4574883ec4048c740d8feffffff",       True,  "жребият на групите"),
    ("SETCL",    0x1522B50, "48895c240848896c24104889742418",         True,  "set_clubs - влизане в елиминациите"),
    ("PROG",     0x1345CC0, "488bc45541564157488bec4883ec60",         True,  "прогресията между фазите"),
    ("STAND",    0x0AF72B0, "488bc4554154415541564157488bec",         True,  "екранът с класирането (36 реда)"),
    ("GNAME",    0x0AF53E0, "40574883ec6048c7442428feffffff",         True,  "надпис League Phase вместо Group A"),
    ("CURPH",    0x150C3C0, "885424105556574154415541564157",         True,  "текущата фаза (Competition Info)"),
    ("PHKIND",   0x150AF30, "8954241048894c2408535556574154",         True,  "вид на фазата (Competition Info)"),
    ("PHNAME",   0x14CB830, "4881ec38010000488d542420e87f230300",     True,  "име Play-offs"),
    ("GSTAGE",   0x151BE10, "4057415641574883ec4048c7442420feffffff", True,  "етап на групите"),
    ("TEARDOWN", 0x1314350, "4889542410555657415441554156",           False, "юлското закриване (само за Конференциите)"),
    ("CARRY",    0x134A680, "83ef01740983ff030f851c020000",           False, "пренос на точки в разделена лига (НЕ ни трябва)"),
]

# Кръпките на bg_link 2.31 (RVA, дължина, какво)
BG_LINK = [
    (0x14F82B4, 2,  "връзката между дивизиите (jne -> nop nop)"),
    (0x134A66E, 32, "пренос на точките от редовния сезон"),
    (0x1580391, 4,  "байтове в таблицата с датите (170/171/173)"),
    (0xB1B6BC,  5,  "Team of the Season, повикване"),
    (0x1510C67, 5,  "целта на борда -> 171, повикване"),
    (0xF45061,  5,  "резултатите на двата баража, сравнение"),
    (0x159FB51, 64, "пещера"),
    (0x11400B5, 64, "пещера"),
    (0x1140329, 64, "пещера"),
]


def sections(pe):
    e_lfanew = struct.unpack_from("<I", pe, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe, e_lfanew + 6)[0]
    optsz = struct.unpack_from("<H", pe, e_lfanew + 20)[0]
    off = e_lfanew + 24 + optsz
    out = []
    for i in range(nsec):
        s = off + i * 40
        name = pe[s:s + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", pe, s + 8)
        out.append((name, va, max(vsize, rawsize), rawptr, rawsize))
    return out


def rva_to_off(secs, rva):
    for name, va, size, rawptr, rawsize in secs:
        if va <= rva < va + size:
            if rva - va >= rawsize:
                return None, name
            return rawptr + (rva - va), name
    return None, "?"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Games\eFootball PES 2021\PES2021.exe"
    pe = open(path, "rb").read()
    secs = sections(pe)
    print("exe:", path, "-", len(pe), "байта")
    print("секции:", ", ".join("%s@%X" % (n, va) for n, va, _, _, _ in secs))
    print()

    bad_needed = 0
    for name, rva, hexs, needed, what in SITES:
        want = bytes.fromhex(hexs)
        off, sec = rva_to_off(secs, rva)
        if off is None:
            got = None
            mark = "НЯМА НА ДИСКА (" + sec + ")"
        else:
            got = pe[off:off + len(want)]
            mark = "OK" if got == want else "РАЗЛИЧНО"
        if mark != "OK" and needed:
            bad_needed += 1
        print("%-9s 0x%X  %-8s %s%s" % (name, BASE + rva, mark, what, "" if needed else "  [не е за 1-ва фаза]"))
        if got is not None and got != want:
            print("          очаквано %s" % want.hex(" "))
            print("          има      %s" % got.hex(" "))

    print()
    print("Застъпване с bg_link 2.31:")
    clash = 0
    for name, rva, hexs, needed, what in SITES:
        a0, a1 = rva, rva + 14
        for b, n, bw in BG_LINK:
            if a0 < b + n and b < a1:
                clash += 1
                print("  %-9s 0x%X  <->  bg_link 0x%X (%s)%s" % (name, BASE + rva, BASE + b, bw,
                      "" if needed else "  - изрязва се от нашия DLL"))
    if not clash:
        print("  няма")

    print()
    if bad_needed == 0:
        print("РЕЗУЛТАТ: всички места, нужни за UCL/UEL, съвпадат. Кодът е същият като на FL_2026.")
    else:
        print("РЕЗУЛТАТ: %d нужни места се различават - адресите трябва да се пренесат." % bad_needed)


if __name__ == "__main__":
    main()
