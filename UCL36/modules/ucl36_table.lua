-- UCL36 B2 (Champions e Europa League): la classifica della fase a campionato a 36
-- nella schermata del campionato del gioco (quella della Serie A, che scorre).
-- Tre agganci nel codice del gioco (piu' due facoltativi, A4 per l'etichetta del menu e A5 per la
-- classifica del dopo partita, e due pezzi senza evento per l'intestazione della giornata, in fondo):
--   A1 creatore della schermata dei gironi: se il torneo scelto nel menu e' la
--      Champions (chiave 2) o l'Europa League (chiave 3) e la sua fase a 36 e' in
--      memoria, crea la schermata del campionato;
--   A2 "open" della schermata del campionato: se la competizione dell'oggetto e'
--      quella a eliminazione della coppa per cui A1 ha acceso (comp 4 Champions,
--      comp 6 Europa League), scrive le 36 righe nella tabella classifica del suo
--      record dei risultati (che il gioco lascia vuota), una volta sola per schermata;
--   A3 distruttore della schermata: rimette la tabella com'era.
-- La classifica si calcola qui dalle partite in memoria, con i criteri di
-- standings.py; l'ultimo (coefficiente) viene da table.json, scritto dal worker.
-- Riferimento Python, tenuto uguale dai test: src/ucl36/table_view.py.
-- Guasto (per tutto il modulo, non per coppa): dopo TRIP_CALLS chiamate di A2 per lo stesso oggetto (o una schermata di
-- un'altra competizione dopo che A1 ha acceso) il modulo smette di intervenire fino
-- al riavvio: A2 non fa piu' niente e A1 non accende piu' l'interruttore.
-- Etichetta del menu (b2-4, opzione B della ricerca docs/research/2026-10-06-menu-fase-campionato.md):
-- la voce che apre la classifica si chiama "Fase campionato" invece di "Fase a gironi" per la Champions
-- e l'Europa League, solo mentre la loro fase a 36 e' in memoria. Solo scritture in memoria: i 16 byte
-- della stringa 0x44C0003 ("Scheda giocatore", inutilizzata) e il dword "nome della fase" del record della
-- competizione; un aggancio all'apertura del sottomenu (A4) decide ogni volta. Si scrive solo dopo aver
-- controllato il valore atteso; se un controllo non passa non si scrive niente e resta l'etichetta nativa.
-- Intestazione della giornata (b2-5, ricerca docs/research/2026-10-07-etichetta-calendario-e-classifica-dopo-partita.md):
-- nel calendario, nei risultati della giornata e nelle notizie "Fase a gironi - Giornata N" e' l'id 0x3A20011
-- scritto a mano in due blocchi gemelli (0x14152A746 e 0x140CADFB1), uguale per tutte le coppe a gironi. I due
-- blocchi sono sostituiti da due pezzi di codice SENZA evento Lua (girano a ogni riga disegnata) che fanno quello
-- che faceva il gioco e poi, solo con la chiave 2 o 3 e solo se il byte di quella coppa non e' zero, mettono
-- l'id 0x44C0003. I due byte li tiene il Lua: 1 solo se il modulo e' attivo, la fase a 36 della coppa e' in
-- memoria e la voce 0x44C0003 contiene "Fase campionato"; li aggiorna all'avvio, in A4 e nel giro del calendario.
-- Classifica del dopo partita (b2-5, stessa ricerca): dopo una partita la schermata dei gironi nasce da un altro
-- creatore, che non passa da A1; i due percorsi si incontrano in 0x140AF4E20. A5, all'ingresso di quella
-- funzione, e' fatto come A1 e salta al gemello del campionato 0x140AED610 con gli stessi tre argomenti; accende
-- solo dopo una partita (terzo argomento diverso da 0: dal menu ha gia' deciso A1), con il sottoindice 0..2 e con
-- la competizione scelta 0xFFFF (lo stato del menu: la schermata prende da sola la comp 4 o 6) oppure un girone
-- nativo della coppa; altrimenti scrive una riga con i valori. Il secondo e' lo stato vero del dopo partita
-- (prova del 2026-10-08, par. 6 della ricerca): l'aggiornamento del dopo partita mette nel modello il girone
-- della partita appena giocata (0x803), e la schermata del campionato nasce con quell'id in [oggetto + 0xA8].
-- Nel modello non si scrive niente (quella parola la leggono altre otto schermate): A5 passa ad A2 la coppa e
-- l'id visto, e A2, alla prima apertura di un oggetto che ha proprio quell'id, prima scrive le 36 righe nella
-- tabella della comp 4 o 6 e solo dopo porta [oggetto + 0xA8] a 4 o 6 (2 byte, riletti). Se qualcosa non torna
-- prima di quel punto non si scrive niente e non si va in guasto: resta la classifica a 4 righe del girone, che
-- ha "avanti" (la comp 4 senza le nostre righe sarebbe uno schermo nero).
-- Sider non ha pcall: ogni lettura passa da readable().
local m = { version = "b2-7" }
local IMAGE_BASE, ROOT_RVA, MODEL_PTR_OFF, RESULTS_PTR_OFF = 0x140000000, 0x3705E10, 0x48, 0x78
local EVENT_OFF, EVENT_SIZE, EVENT_COUNT = 0xE9FF08, 0x254, 13000
-- competizioni del modello (memlayout.py): 300 record; id (u16) in testa, competizione madre, chiave del torneo
local COMP_OFF, COMP_SIZE, COMP_COUNT, COMP_PARENT_OFF, COMP_KEY_OFF = 0xC12E9C, 0x314, 300, 0x76, 0x80
local KEY_OFF = 0x1787B5C                  -- chiave del torneo scelto nel menu (u32)
local CHOSEN_OFF, SUB_OFF = 0x1787B60, 0x1787B64     -- competizione scelta (u16, 0xFFFF = nessuna) e sottoindice (u32)
-- Le due coppe: chiave del torneo (menu e voce dei risultati), bit bassi dei gironi
-- (g << 10) | low con g = 1..groups, competizione a eliminazione (il cui record ha la
-- tabella che usiamo e che la schermata ha in [oggetto + 0xA8]), chiave in table.json.
-- Riferimento Python: cups.py (UCL, UEL).
-- `stage` = dword "nome della fase" (+0x40) del record della competizione a gironi (comp 3 e 5) nella
-- tabella in .data a 0x1434FDF00.
local CUPS = {
    ucl = { name = "Champions", key = 2, low = 3, groups = 8, ko = 4, json = "ucl", written = "", stage = 0x1434FE150 },
    uel = { name = "Europa League", key = 3, low = 5, groups = 12, ko = 6, json = "uel", written = " per la comp 6",
            stage = 0x1434FE360 },
}
local CUP_LIST = { CUPS.ucl, CUPS.uel }
local MATCHES, TEAMS, TEAM_MATCHES = 144, 36, 8
-- tabella dei risultati: [radice + 0x78] = 100 voci da 0xB4 (una per torneo:
-- chiave + 2 blocchi-stagione), poi 600 record da 0x187C
-- La voce di un torneo e' una chiave u32 e DUE blocchi-stagione da 0x58 byte
-- { chiave u32 (0xFFFFFFFF = vuoto), anno u32, 20 indici }; il gioco prende il
-- blocco con l'anno piu' alto (16 bit bassi) e il primo indice il cui record ha
-- come id la competizione (0x14159EBF0 + 0x14158DF30).
local ENTRY_SIZE, ENTRY_COUNT = 0xB4, 100
local BLOCK_SIZE, BLOCK_IDS, EMPTY_KEY = 0x58, 20, 0xFFFFFFFF
local RECORDS_OFF, STRIDE, RECORD_COUNT, BLOCK_SIZE_FIELD = 0x4650, 0x187C, 600, 0x3AFFE0
-- tabella classifica dentro il record: 48 righe da 20 byte, numero di righe,
-- 48 righe della classifica precedente, coda
local TABLE_OFF, ROW, ROWS = 0x318, 20, 48
local COUNT_OFF, PREV_OFF, COUNT2_OFF, MATCHDAY_OFF, TABLE_SIZE = 0x3C0, 0x3C4, 0x784, 0x78C, 0x790
local NO_MATCHDAY = 0x37
local EMPTY_ROW = string.rep("\255", 8) .. string.rep("\0", 12)
local OBJ_COMP_OFF = 0xA8                  -- competizione della schermata del campionato (u16)
local TRIP_CALLS = 120                     -- chiamate di A2 per lo stesso oggetto, poi guasto (circa 2 secondi)
local OBJ_VEC_OFF, RETRY_EVERY = 0x90, 30      -- vettore squadre dell'oggetto (inizio, fine); ogni quante chiamate si riprova
local GLOBAL_PTR, GLOBAL_COUNT_OFF, OBJ_LIST_OFF, LIST_COUNT_OFF = 0x1436F9DE0, 0x90, 0x88, 0x98   -- F1 e F2 della open
local MEM_COMMIT, PAGE_NOACCESS, PAGE_GUARD = 0x1000, 0x01, 0x100
local LEAGUE_CREATOR = 0x140AED680         -- MenuModeCmnStandingsMenu::CreateObject
local LEAGUE_AFTER = 0x140AED610           -- gemello di 0x140AF4E20 per la schermata del campionato: stessi tre argomenti
local MARKER = "UCL36-TABLE-B2\0\0"        -- 16 byte prima di ogni nostro pezzo di codice
local SITES = {
    create = { addr = 0x140AF4E90, event = "custom:ucl36_table_create", target = LEAGUE_CREATOR,
               original = "\x48\x89\x5C\x24\x08\x57\x48\x83\xEC\x20\x48\x8B\xFA\x48\x8B\xD9" },
    open = { addr = 0x140AEDA10, event = "custom:ucl36_table_open",
             original = "\x48\x8B\xC4\x55\x41\x54\x41\x55\x41\x56\x41\x57\x48\x8D\x68\xA1" },
    close = { addr = 0x140AED520, event = "custom:ucl36_table_close",
              original = "\x40\x57\x48\x83\xEC\x30\x48\xC7\x44\x24\x20\xFE\xFF\xFF\xFF" },
}
-- A4 (facoltativo): "open" del sottomenu della competizione; i primi 18 byte sono istruzioni intere e
-- senza indirizzi relativi a rip (la ricerca li ha letti nel file)
SITES.menu = { addr = 0x140AFF810, event = "custom:ucl36_table_menu",
               original = "\x48\x8B\xC4\x55\x57\x41\x56\x48\x8D\x68\xA1\x48\x81\xEC\x90\x00\x00\x00" }
-- A5 (facoltativo): ingresso di 0x140AF4E20(nome, flag, solo-avanti), dove si incontrano il creatore del menu
-- (A1, terzo argomento 0) e quello del dopo partita (terzo argomento 1); i primi 15 byte sono istruzioni intere,
-- senza indirizzi relativi a rip, e sono gli stessi del gemello 0x140AED610
SITES.after = { addr = 0x140AF4E20, event = "custom:ucl36_table_after", target = LEAGUE_AFTER,
                original = "\x40\x57\x48\x83\xEC\x30\x48\xC7\x44\x24\x20\xFE\xFF\xFF\xFF" }
local EXTRA_ORDER = { "menu", "after" }
-- Parole dei due agganci facoltativi per le righe del log: prefisso, evento mancante, cosa resta nativo.
local EXTRA_TEXT = {
    menu = { "etichetta", "evento del menu non disponibile", "la voce di menu resta quella del gioco" },
    after = { "classifica", "evento del dopo partita non disponibile", "dopo la partita resta la schermata dei gironi" },
}
-- I due blocchi che scelgono "Fase a gironi" per l'intestazione della giornata: un solo ingresso (dall'alto),
-- una sola uscita (`exit`), nessun indirizzo relativo a rip. `cmp` = "cmp <registro della chiave>, imm8" senza
-- l'immediato (r14d nel primo, ebx nel secondo). Il primo ha due salti corti all'uscita (`two_exits`), che nel
-- nostro pezzo vanno rifatti; il secondo si copia tale e quale (finisce con lea rcx, [rbp-0x30]).
local LABEL_SITES = {
    { addr = 0x14152A746, exit = 0x14152A77C, cmp = "\x41\x83\xFE", two_exits = true,
      original = "\x0F\xB6\x9D\x88\x00\x00\x00\x48\x8D\x4D\xB0\x84\xDB\x74\x07\xBA\x28\x00\x51\x00\xEB\x20"
          .. "\xBA\x11\x00\xA2\x03\xEB\x19" },
    { addr = 0x140CADFB1, exit = 0x140CADFC9, cmp = "\x83\xFB",
      original = "\x83\xFB\x05\x74\x0A\x83\xFB\x30\xBA\x11\x00\xA2\x03\x75\x05\xBA\x5F\x00\xA2\x03\x48\x8D\x4D\xD0" },
}
local PHASE_EVERY = 10000                    -- ogni quanti ms il giro del calendario ricontrolla "fase a 36 in memoria"
local TEXT_MGR_PTR = 0x143704DE8             -- gestore dei testi (singleton)
local NATIVE_ID, LABEL_ID = 0x3A20011, 0x44C0003    -- "Fase a gironi"; "Scheda giocatore" (Xbox Live), che usiamo
local PREV_ID = 0x44C0002                    -- "Profilo giocatore" (Xbox Live): nel file sta subito prima di 0x44C0003
local TEXT_CAP = 64                          -- byte massimi di una voce di testo che accettiamo
-- L'etichetta in ogni lingua del gioco (b2-6). slot e prev = i testi di 0x44C0003 e 0x44C0002 in quella lingua,
-- presi dai 18 all.str veri: riconoscono la lingua. label = il nome della fase a 36 (byte UTF-8), name = lo
-- stesso in ASCII per il log. Dove l'etichetta non entra nella voce 0x44C0003 (chi, eng, gre, nld, por, zha) si
-- usa anche lo spazio di 0x44C0002, che la precede: vedi ensure_label_text.
local LABELS = {
    { lang = "ara",     name = "Marhalat al-dawri",
      slot = "\216\168\216\183\216\167\217\130\216\169 \216\167\217\132\217\132\216\167\216\185\216\168", prev = "\217\133\217\132\217\129 \216\170\216\185\216\177\217\138\217\129 \216\167\217\132\217\132\216\167\216\185\216\168",
      label = "\217\133\216\177\216\173\217\132\216\169 \216\167\217\132\216\175\217\136\216\177\217\138" },
    { lang = "bra",     name = "Fase de liga",
      slot = "Cart\195\163o de jogador", prev = "Perfil do jogador",
      label = "Fase de liga" },
    { lang = "chi",     name = "Lian sai jie duan (trad.)",
      slot = "\231\142\169\229\174\182\229\141\161", prev = "\231\142\169\229\174\182\232\168\173\229\174\154\230\170\148",
      label = "\232\129\175\232\179\189\233\154\142\230\174\181" },
    { lang = "eng",     name = "League phase",
      slot = "Gamer card", prev = "Gamer profile",
      label = "League phase" },
    { lang = "fra",     name = "Phase de ligue",
      slot = "Carte du joueur", prev = "Profil du joueur",
      label = "Phase de ligue" },
    { lang = "ger",     name = "Ligaphase",
      slot = "Spielerkarte", prev = "Spielerprofil",
      label = "Ligaphase" },
    { lang = "gre",     name = "Fasi protathlimatos",
      slot = "\206\154\206\172\207\129\207\132\206\177 \207\128\206\177\206\175\206\186\207\132\206\183", prev = "\206\160\207\129\206\191\207\134\206\175\206\187 \207\128\206\177\206\175\206\186\207\132\206\183",
      label = "\206\166\206\172\207\131\206\183 \207\128\207\129\207\137\207\132\206\177\206\184\206\187\206\174\206\188\206\177\207\132\206\191\207\130" },
    { lang = "ita",     name = "Fase campionato",
      slot = "Scheda giocatore", prev = "Profilo giocatore",
      label = "Fase campionato" },
    { lang = "jpn",     name = "Riigu feezu",
      slot = "\227\130\178\227\131\188\227\131\158\227\131\188 \227\130\171\227\131\188\227\131\137", prev = "\227\130\178\227\131\188\227\131\158\227\131\188\227\131\151\227\131\173\227\131\149\227\130\163\227\131\188\227\131\171",
      label = "\227\131\170\227\131\188\227\130\176\227\131\149\227\130\167\227\131\188\227\130\186" },
    { lang = "kor",     name = "Rigeu peijeu",
      slot = "\234\178\140\236\157\180\235\168\184 \236\185\180\235\147\156", prev = "\234\178\140\236\157\180\235\168\184 \237\148\132\235\161\156\237\149\132",
      label = "\235\166\172\234\183\184 \237\142\152\236\157\180\236\166\136" },
    { lang = "mex/spa", name = "Fase liga",
      slot = "Tarjeta de jugador", prev = "Perfil de jugador",
      label = "Fase liga" },
    { lang = "nld",     name = "Competitiefase",
      slot = "Gamerkaart", prev = "Gamerprofiel",
      label = "Competitiefase" },
    { lang = "por",     name = "Fase de liga",
      slot = "Gamercard", prev = "Perfil de jogador",
      label = "Fase de liga" },
    { lang = "rus",     name = "Obshchiy etap",
      slot = "\208\154\208\176\209\128\209\130\208\176 \208\184\208\179\209\128\208\190\208\186\208\176", prev = "\208\159\209\128\208\190\209\132\208\184\208\187\209\140 \208\184\208\179\209\128\208\190\208\186\208\176",
      label = "\208\158\208\177\209\137\208\184\208\185 \209\141\209\130\208\176\208\191" },
    { lang = "swe",     name = "Ligafas",
      slot = "Spelarfakta", prev = "Spelarprofil",
      label = "Ligafas" },
    { lang = "tur",     name = "Lig asamasi",
      slot = "Oyuncu kart\196\177", prev = "Oyuncu profili",
      label = "Lig a\197\159amas\196\177" },
    { lang = "zha",     name = "Lian sai jie duan (sempl.)",
      slot = "\231\142\169\229\174\182\229\141\161", prev = "\231\142\169\229\174\182\233\133\141\231\189\174\230\150\135\228\187\182",
      label = "\232\129\148\232\181\155\233\152\182\230\174\181" },
}
local MAP_CAP, SECTION_CAP = 64, 65536       -- passi massimi della ricerca nella mappa; voci massime di una sezione
local SITE_ORDER = { "close", "open", "create" }   -- il creatore per ultimo: e' lui che accende tutto
local KEYS = { "points", "gd", "gf", "away_gf", "won", "away_won", "opp_points", "opp_gd", "opp_gf", "coef" }

local runtime_dir = nil
local switch_addr = nil                    -- byte letto da A1: 1 = crea la schermata del campionato
local after_switch = nil                   -- lo stesso per A5 (dopo la partita)
local flag_addr = nil                      -- byte letti dai due pezzi dell'intestazione: { [coppa] = indirizzo }; nil = pezzi spenti
local phase = {}                           -- ultimo esito del controllo "fase a 36 in memoria", per coppa
local pending = {}                         -- gironi della coppa non ancora sorteggiati (b2-7), per coppa
local next_phase = 0                       -- quando il giro del calendario lo rifa'
local last_after_note, last_flag_note = nil, nil     -- come last_note, per A5 e per l'intestazione
local ledger = nil                         -- tabella scritta da noi: { addr, before, obj, cup }
local last_note = nil
local last_label_note = nil                      -- come last_note, per le righe dell'etichetta
local switch_cup = nil                       -- coppa per cui A1 ha acceso l'interruttore: la prossima apertura deve essere la sua comp a eliminazione
local handover = nil                         -- consegna di A5 ad A2 dopo una partita: { cup, id = girone visto nel modello }
local tripped = false                        -- guasto: dura fino al ricaricamento del modulo
local screen = nil                           -- schermata di cui A2 ha gia' lavorato: { obj, calls, written, rewrote, cup }
local next_sweep = 0

if ffi ~= nil then
    -- nomi privati (UCL36T_...): VirtualQuery e' gia' dichiarata, con altri tipi,
    -- dalla libreria memory di Sider e dalla guardia nello spazio ffi condiviso
    ffi.cdef[[
        size_t UCL36T_VirtualQuery(const void* lpAddress, void* lpBuffer, size_t dwLength)
            __asm__("VirtualQuery");
        unsigned long long GetTickCount64(void);
        unsigned long GetCurrentThreadId(void);
    ]]
end

local function u16(s, o)
    local a, b = s:byte(o + 1, o + 2)
    return a + b * 256
end

local function u32(s, o)
    local a, b, c, d = s:byte(o + 1, o + 4)
    return a + b * 256 + c * 65536 + d * 16777216
end

local function u64(s, o)
    return u32(s, o) + u32(s, o + 4) * 4294967296
end

local function pack(n, size)
    local out = {}
    for i = 1, size do
        out[i] = string.char(n % 256)
        n = math.floor(n / 256)
    end
    return table.concat(out)
end

local function p32(n) return pack(n, 4) end
local function p64(n) return pack(n, 8) end

-- Tutte le pagine di [addr, addr + size) sono impegnate e leggibili. Prima di tutto un controllo
-- dei limiti: memory.read di Sider non valida gli indirizzi e con numeri enormi (addr + size == addr
-- in virgola mobile) il ciclo sotto non girerebbe e darebbe "leggibile"; fuori dallo spazio utente
-- (0x10000 .. 0x7FFFFFFF0000) o con dimensione non positiva si rifiuta, senza interrogare nessuna pagina.
local USER_MIN, USER_MAX = 0x10000, 0x7FFFFFFF0000
function m.readable(addr, size)
    if type(addr) ~= "number" or type(size) ~= "number" then return false end
    if not (addr >= USER_MIN and size > 0 and addr + size <= USER_MAX) then return false end   -- anche NaN
    local mbi = ffi.new("uint64_t[6]")     -- MEMORY_BASIC_INFORMATION (48 byte)
    local stop = addr + size
    while addr < stop do
        if ffi.C.UCL36T_VirtualQuery(ffi.cast("void*", addr), mbi, 48) == 0 then return false end
        local words = ffi.cast("uint32_t*", mbi)
        local state, protect = words[8], words[9]
        if state ~= MEM_COMMIT then return false end
        if bit.band(protect, PAGE_NOACCESS) ~= 0 or bit.band(protect, PAGE_GUARD) ~= 0 then return false end
        addr = tonumber(mbi[0]) + tonumber(mbi[3])      -- base + dimensione della regione
    end
    return true
end

function m.tick()
    return tonumber(ffi.C.GetTickCount64())
end

local function rd(addr, size)
    if not m.readable(addr, size) then return nil end
    return memory.read(addr, size)
end

local function pointer(addr)
    local s = rd(addr, 8)
    if not s then return nil end
    local p = u64(s, 0)
    if p == 0 then return nil end
    return p
end

-- Modello della ML e radice; nil senza ML o se un puntatore non si legge.
local function model()
    local root = pointer(IMAGE_BASE + ROOT_RVA)
    if not root then return nil end
    local mdl = pointer(root + MODEL_PTR_OFF)
    if not mdl then return nil end
    return mdl, root
end

local function team_of(raw)
    local t = math.floor(raw / 16384) % 131072
    if t > 0 and t < 10000 then return t end
    return nil
end

-- Fase a campionato di una coppa (default Champions) dagli eventi (stringa da 13000
-- eventi): { teams = le 36 in ordine di id, results = partite giocate, codes =
-- squadra -> codice a 32 bit }, oppure nil, il motivo e il numero di partite dei gironi della coppa viste
-- (0 = gironi non ancora sorteggiati) se la fase a 36 non e' in memoria.
function m.league_state(events, cup)
    cup = cup or CUPS.ucl
    local results, count, codes, n = {}, {}, {}, 0
    for eid = 0, EVENT_COUNT - 1 do
        local o = eid * EVENT_SIZE
        if u16(events, o) == eid then
            local packed = u32(events, o + 4)
            local comp = packed % 65536
            local group = math.floor(comp / 1024)
            if comp % 1024 == cup.low and group >= 1 and group <= cup.groups then
                n = n + 1
                local home_raw, away_raw = u32(events, o + 0x14), u32(events, o + 0x18)
                local home, away = team_of(home_raw), team_of(away_raw)
                if not home or not away then return nil, "partita " .. eid .. " senza squadre", n end
                codes[home] = codes[home] or home_raw
                codes[away] = codes[away] or away_raw
                count[home] = (count[home] or 0) + 1
                count[away] = (count[away] or 0) + 1
                if math.floor(packed / 0x40000000) % 2 == 1 then
                    results[#results + 1] = { home = home, away = away,
                                              hg = events:byte(o + 0x1C + 1), ag = events:byte(o + 0x1F + 1) }
                end
            end
        end
    end
    if n ~= MATCHES then return nil, n .. " partite, attese " .. MATCHES, n end
    local teams = {}
    for team, c in pairs(count) do
        if c ~= TEAM_MATCHES then return nil, "squadra " .. team .. " con " .. c .. " partite", n end
        teams[#teams + 1] = team
    end
    if #teams ~= TEAMS then return nil, #teams .. " squadre, attese " .. TEAMS, n end
    table.sort(teams)
    return { teams = teams, results = results, codes = codes }
end

local function add(row, gf, ga)
    row.played = row.played + 1
    row.gf = row.gf + gf
    row.ga = row.ga + ga
    if gf > ga then
        row.won = row.won + 1
        row.points = row.points + 3
    elseif gf == ga then
        row.drawn = row.drawn + 1
        row.points = row.points + 1
    else
        row.lost = row.lost + 1
    end
end

-- Le 36 righe dalla prima all'ultima: criteri e ordine di standings.table (la
-- disciplina non e' in memoria). `order` = squadre nell'ordine dell'ultimo
-- criterio (table.json), nil = solo l'id squadra.
function m.standings(state, order)
    local rows, opponents = {}, {}
    for _, t in ipairs(state.teams) do
        rows[t] = { team = t, played = 0, won = 0, drawn = 0, lost = 0, gf = 0, ga = 0,
                    away_gf = 0, away_won = 0, points = 0, opp_points = 0, opp_gd = 0, opp_gf = 0, coef = 0 }
        opponents[t] = {}
    end
    for _, r in ipairs(state.results) do
        local h, a = rows[r.home], rows[r.away]
        opponents[r.home][#opponents[r.home] + 1] = a
        opponents[r.away][#opponents[r.away] + 1] = h
        add(h, r.hg, r.ag)
        add(a, r.ag, r.hg)
        a.away_gf = a.away_gf + r.ag
        if r.ag > r.hg then a.away_won = a.away_won + 1 end
    end
    if order then
        for i, t in ipairs(order) do
            if rows[t] then rows[t].coef = #order - i + 1 end
        end
    end
    local list = {}
    for _, t in ipairs(state.teams) do
        local row = rows[t]
        row.gd = row.gf - row.ga
        list[#list + 1] = row
    end
    for _, row in ipairs(list) do
        for _, o in ipairs(opponents[row.team]) do
            row.opp_points = row.opp_points + o.points
            row.opp_gd = row.opp_gd + o.gd
            row.opp_gf = row.opp_gf + o.gf
        end
    end
    table.sort(list, function(x, y)
        for _, k in ipairs(KEYS) do
            if x[k] ~= y[k] then return x[k] > y[k] end
        end
        return x.team < y.team
    end)
    return list
end

-- La tabella da scrivere sopra `before`: le righe in classifica attuale e
-- precedente, numero di righe, giornata (indice dell'ultima giocata, 0x37 = nessuna).
function m.pack_table(before, rows, codes)
    local parts, most = {}, 0
    for i, r in ipairs(rows) do
        parts[i] = p32(codes[r.team]) .. p32(i)
            .. p32(r.points + r.won * 256 + r.lost * 16384 + r.drawn * 1048576)
            .. p32(r.gf + r.ga * 4096 + r.played * 16777216) .. p32(0)
        if r.played > most then most = r.played end
    end
    local body = table.concat(parts)
    local used = #rows * ROW
    local matchday = NO_MATCHDAY
    if most > 0 then matchday = most - 1 end
    return body .. before:sub(used + 1, COUNT_OFF) .. p32(#rows)
        .. body .. before:sub(PREV_OFF + used + 1, COUNT2_OFF) .. p32(#rows)
        .. before:sub(COUNT2_OFF + 5, MATCHDAY_OFF) .. p32(matchday)
end

-- La tabella senza righe, come la tiene il gioco.
function m.emptied(tbl)
    local rows = string.rep(EMPTY_ROW, ROWS)
    return rows .. p32(0) .. rows .. p32(0) .. tbl:sub(COUNT2_OFF + 5, MATCHDAY_OFF) .. p32(NO_MATCHDAY)
end

-- Squadre dell'ultimo criterio da table.json (chiave della coppa, "ucl" o "uel":
-- [id, ...]); nil se il file manca o non contiene tutte le 36.
function m.parse_order(text, teams, cup)
    cup = cup or CUPS.ucl
    local list = text and text:match('"' .. cup.json .. '"%s*:%s*%[([^%]]*)%]')
    if not list then return nil end
    local order, seen = {}, {}
    for id in list:gmatch("%d+") do
        order[#order + 1] = tonumber(id)
        seen[tonumber(id)] = true
    end
    for _, t in ipairs(teams) do
        if not seen[t] then return nil end
    end
    return order
end

local function read_order(teams, cup)
    local f = io.open(runtime_dir .. "\\table.json", "r")
    if not f then return nil end
    local text = f:read("*a")
    f:close()
    return m.parse_order(text, teams, cup)
end

local function paused()
    local f = io.open(runtime_dir .. "\\pausa", "r")
    if not f then return false end
    f:close()
    return true
end

-- Byte dell'intestazione della giornata di una coppa: si scrive solo se cambia.
local function set_flag(cup, on)
    if not flag_addr then return end
    local want = on and "\1" or "\0"
    if rd(flag_addr[cup], 1) ~= want then memory.write(flag_addr[cup], want) end
end

local function clear_flags()
    for _, cup in ipairs(CUP_LIST) do set_flag(cup, false) end
end

-- Modulo fermo (guasto o pausa): chi se ne accorge spegne anche l'intestazione della giornata.
local function stopped()
    if tripped or paused() then
        clear_flags()
        return true
    end
    return false
end

-- model() per i gestori degli eventi e per il giro del calendario: senza carriera (si e' usciti dalla Master
-- League) l'intestazione della giornata si spegne, l'esito delle fasi si scorda e il controllo e' da rifare subito.
local function career()
    local mdl, root = model()
    if not mdl then
        clear_flags()
        phase, pending, next_phase = {}, {}, 0
    end
    return mdl, root
end

-- I valori che decidono quale competizione prende la schermata del campionato (costruttore 0x140AED280), per le
-- righe di A1 e A5: "n/d" se non si leggono.
local function state_text(cup, chosen, sub)
    return string.format("chiave %d, competizione scelta %s, sottoindice %s", cup.key,
        chosen and string.format("0x%X", u16(chosen, 0)) or "n/d", sub and string.format("0x%X", u32(sub, 0)) or "n/d")
end

-- Blocco dei risultati e voce della coppa: base, voci (stringa), offset della prima
-- voce con la chiave; nil e il motivo se non ci sono.
local function results_entries(root, cup)
    local base = pointer(root + RESULTS_PTR_OFF)
    if not base then return nil, "tabella dei risultati assente" end
    local sign = rd(base - 8, 4)
    if not sign or u32(sign, 0) ~= BLOCK_SIZE_FIELD then return nil, "tabella dei risultati non riconosciuta" end
    local entries = rd(base, ENTRY_SIZE * ENTRY_COUNT)
    if not entries then return nil, "tabella dei risultati non leggibile" end
    for k = 0, ENTRY_COUNT - 1 do
        local e = k * ENTRY_SIZE
        if u32(entries, e) == cup.key then return base, entries, e end
    end
    return nil, cup.name .. " assente dalla tabella dei risultati"
end

-- Il blocco-stagione che il gioco sceglie nella voce `e`: valido se la chiave non e'
-- 0xFFFFFFFF e l'anno (16 bit bassi) non e' 0xFFFF; vince l'anno piu' alto, a parita' il primo.
local function game_block(entries, e)
    local best, best_year = nil, 0
    for k = 0, 1 do
        local b = e + 4 + k * BLOCK_SIZE
        local year = u16(entries, b + 4)
        if u32(entries, b) ~= EMPTY_KEY and year ~= 0xFFFF and (not best or year > best_year) then
            best, best_year = b, year
        end
    end
    return best
end

-- Il primo record (indice < 600, lista da b+8, al massimo 20, chiusa da 0xFFFFFFFF) del
-- blocco `b` che ha `cid` nei 16 bit bassi della testa: il suo indirizzo, o nil.
local function block_record(base, entries, b, cid)
    for i = 0, BLOCK_IDS - 1 do
        local idx = u32(entries, b + 8 + i * 4)
        if idx == EMPTY_KEY then break end
        if idx < RECORD_COUNT then
            local rec = base + RECORDS_OFF + idx * STRIDE
            local head = rd(rec, 4)
            if head and u16(head, 0) == cid then return rec end
        end
    end
    return nil
end

-- Indirizzo della tabella classifica che la schermata legge per la comp a eliminazione
-- della coppa (default Champions, comp 4), trovata come fa il gioco (0x141579B90); nil e
-- il motivo se non c'e'. Con `cid` la tabella di un'altra competizione dello stesso torneo (un girone).
local function find_table(root, cup, cid)
    cup = cup or CUPS.ucl
    cid = cid or cup.ko
    local base, entries, e = results_entries(root, cup)
    if not base then return nil, entries end
    local b = game_block(entries, e)
    if not b then return nil, cup.name .. " senza blocco-stagione valido nella tabella dei risultati" end
    local rec = block_record(base, entries, b, cid)
    if not rec then return nil, "record dei risultati della comp " .. cid .. " non trovato" end
    return rec + TABLE_OFF
end

-- La competizione `id` e' un girone nativo della coppa con la sua classifica nel gioco: nil. Altrimenti il
-- motivo. Girone = record delle competizioni con la madre uguale al contenitore dei gironi (comp 3 o 5) e la
-- chiave della coppa; la sua tabella dei risultati deve avere almeno una riga (nelle catture 4): e' la schermata
-- che resta se A2 poi non puo' scrivere.
local function group_problem(mdl, root, cup, id)
    local comps = rd(mdl + COMP_OFF, COMP_SIZE * COMP_COUNT)
    if not comps then return "competizioni non leggibili" end
    for i = 0, COMP_COUNT - 1 do
        local o = i * COMP_SIZE
        if u16(comps, o) == id then
            local parent, key = u16(comps, o + COMP_PARENT_OFF), u32(comps, o + COMP_KEY_OFF)
            if parent ~= cup.low or key ~= cup.key then
                return string.format("la competizione scelta non e' un girone della coppa (madre 0x%X, chiave %d)", parent, key)
            end
            local addr = find_table(root, cup, id)
            local count = addr and rd(addr + COUNT_OFF, 4)
            if not count or u32(count, 0) == 0 then return "il girone scelto non ha righe nella tabella del gioco" end
            return nil
        end
    end
    return "la competizione scelta non e' fra le competizioni"
end

-- Le tabelle della comp a eliminazione della coppa di TUTTI e due i blocchi-stagione non
-- vuoti della voce (anche quello che il gioco non legge piu'): per ritrovare una
-- classifica rimasta piena.
local function season_tables(root, cup)
    cup = cup or CUPS.ucl
    local base, entries, e = results_entries(root, cup)
    local out = {}
    if not base then return out end
    for k = 0, 1 do
        local b = e + 4 + k * BLOCK_SIZE
        if u32(entries, b) ~= EMPTY_KEY then
            local rec = block_record(base, entries, b, cup.ko)
            if rec and rec + TABLE_OFF ~= out[1] then out[#out + 1] = rec + TABLE_OFF end
        end
    end
    return out
end

-- Le righe della tabella sono squadre della fase a campionato (classifica
-- nostra rimasta in memoria).
local function ours(tbl, state)
    local n = u32(tbl, COUNT_OFF)
    if n ~= TEAMS then return false end
    for i = 0, n - 1 do
        local team = team_of(u32(tbl, i * ROW))
        if not team or not state.codes[team] then return false end
    end
    return true
end

-- Tutto quello che serve per scrivere la classifica della coppa (default Champions):
-- { addr, before, table, played, first, order }, oppure nil e il motivo. Non scrive niente.
function m.prepare(cup)
    cup = cup or CUPS.ucl
    local mdl, root = model()
    if not mdl then return nil, "nessuna Master League in memoria" end
    local events = rd(mdl + EVENT_OFF, EVENT_SIZE * EVENT_COUNT)
    if not events then return nil, "partite non leggibili" end
    local state, why = m.league_state(events, cup)
    if not state then return nil, "fase a campionato a 36 non in memoria (" .. why .. ")" end
    local addr, missing = find_table(root, cup)
    if not addr then return nil, missing end
    local current = rd(addr, TABLE_SIZE)
    if not current then return nil, "tabella della comp " .. cup.ko .. " non leggibile" end
    local before = current
    if ledger and ledger.addr == addr then
        before = ledger.before
    elseif u32(current, COUNT_OFF) ~= 0 then
        if not ours(current, state) then return nil, "tabella della comp " .. cup.ko .. " non vuota e non nostra" end
        before = m.emptied(current)
    end
    local order = read_order(state.teams, cup)
    local rows = m.standings(state, order)
    return { addr = addr, before = before, table = m.pack_table(before, rows, state.codes),
             played = #state.results, first = rows[1].team, order = order ~= nil }
end

local function note(text)
    if text ~= last_note then
        log("[ucl36] classifica: " .. text)
        last_note = text
    end
end

-- Il registro `ledger` si convalida da solo (non con find_table: dopo un cambio di
-- stagione la ricerca del gioco punta a un altro record): il blocco dei risultati e'
-- ancora quello riconosciuto, l'indirizzo sta nell'area dei record, il record ha la
-- comp a eliminazione della sua coppa (ledger.cup) nella testa e la tabella ha ancora le
-- 36 righe nostre.
local function ledger_valid()
    local mdl, root = model()
    if not mdl then return false end
    local base = pointer(root + RESULTS_PTR_OFF)
    if not base then return false end
    local sign = rd(base - 8, 4)
    if not sign or u32(sign, 0) ~= BLOCK_SIZE_FIELD then return false end
    local first = base + RECORDS_OFF
    local rec = ledger.addr - TABLE_OFF
    if rec < first or rec >= first + RECORD_COUNT * STRIDE or (rec - first) % STRIDE ~= 0 then return false end
    local head = rd(rec, 4)
    if not head or u16(head, 0) ~= ledger.cup.ko then return false end
    local current = rd(ledger.addr, TABLE_SIZE)
    return current ~= nil and u32(current, COUNT_OFF) == TEAMS
end

local function restore(why)
    -- si scrive solo se la tabella e' ancora al suo posto e contiene quello che
    -- abbiamo scritto (36 righe): altrimenti l'indirizzo potrebbe essere altro
    if ledger_valid() then
        memory.write(ledger.addr, ledger.before)
        log("[ucl36] classifica: tabella della comp " .. ledger.cup.ko .. " rimessa com'era (" .. why .. ")")
    else
        log("[ucl36] classifica: tabella della comp " .. ledger.cup.ko
            .. " non piu' al suo posto, niente da rimettere (" .. why .. ")")
    end
    ledger = nil
    screen = nil
end

-- Righe della tabella che il gioco legge adesso per la comp della coppa (nil se non si legge).
local function game_rows(cup)
    local mdl, root = model()
    if not mdl then return nil end
    local addr = find_table(root, cup)
    if not addr then return nil end
    local count = rd(addr + COUNT_OFF, 4)
    return count and u32(count, 0)
end

-- Guasto: una riga col quadro dei valori che decidono F1, F2 e F4 della open (tutti letti
-- con le letture protette; "n/d" se non si leggono), poi il modulo smette di intervenire.
local function trip(obj, calls, cup)
    local rows = game_rows(cup)
    local comp = rd(obj + OBJ_COMP_OFF, 2)
    local g = pointer(GLOBAL_PTR)
    local g90 = g and rd(g + GLOBAL_COUNT_OFF, 4)
    local list = pointer(obj + OBJ_LIST_OFF)
    local list98 = list and rd(list + LIST_COUNT_OFF, 8)
    -- inizio e fine del vettore squadre che la open controlla (F4): indipendenti dal nostro modello
    local vec = rd(obj + OBJ_VEC_OFF, 16)
    log(string.format("[ucl36] classifica: guasto dopo %d chiamate per la stessa schermata: righe nella tabella del gioco %s, "
        .. "competizione dell'oggetto %s, [[0x1436F9DE0]+0x90] %s, [[oggetto+0x88]+0x98] %s, "
        .. "[oggetto+0x90] %s, [oggetto+0x98] %s: il modulo non interviene piu' fino al riavvio",
        calls, rows and tostring(rows) or "n/d", comp and tostring(u16(comp, 0)) or "n/d",
        g90 and tostring(u32(g90, 0)) or "n/d", list98 and tostring(u64(list98, 0)) or "n/d",
        vec and string.format("0x%X", u64(vec, 0)) or "n/d", vec and string.format("0x%X", u64(vec, 8)) or "n/d"))
    tripped = true
    clear_flags()
end

local function cup_by_key(key)
    for _, cup in ipairs(CUP_LIST) do
        if cup.key == key then return cup end
    end
    return nil
end

local function cup_by_ko(cid)
    for _, cup in ipairs(CUP_LIST) do
        if cup.ko == cid then return cup end
    end
    return nil
end

-- Per i testi: la Champions resta senza etichetta, l'Europa League la porta.
local function cup_tag(cup)
    if cup == CUPS.ucl then return "" end
    return " (" .. cup.name .. ")"
end

-- A1: il gioco sta per creare la schermata dei gironi. L'interruttore e' gia'
-- stato azzerato dal codice macchina: resta spento (schermata dei gironi) a
-- meno che tutto sia pronto per la classifica a 36.
function m.on_create(ctx, event_id, registers)
    switch_cup, handover = nil, nil          -- un segnale non sopravvive alla creazione successiva
    if stopped() then return end
    local mdl = career()
    if not mdl then return end
    local key = rd(mdl + KEY_OFF, 4)
    if not key then return end
    local cup = cup_by_key(u32(key, 0))
    if not cup then return end
    local plan, why = m.prepare(cup)
    if not plan then
        note("resta la schermata dei gironi" .. cup_tag(cup) .. ": " .. why)
        return
    end
    memory.write(switch_addr, "\1")
    switch_cup = cup
    -- una riga (non ripetuta se uguale) con lo stato in cui si accende dal menu: e' quello che A5 pretende
    note("dal menu schermata del campionato" .. cup_tag(cup) .. " ("
        .. state_text(cup, rd(mdl + CHOSEN_OFF, 2), rd(mdl + SUB_OFF, 4)) .. ")")
end

-- A5: il gioco sta per creare la schermata dei gironi, dal menu (quando A1 non ha acceso) o dopo una partita.
-- L'interruttore e' gia' stato azzerato dal codice macchina. Dal menu (terzo argomento 0) non fa niente: A1 ha
-- gia' deciso e detto perche'. Dopo una partita si accende con: chiave 2 o 3, sottoindice 0..2 (con uno piu'
-- alto 0x141544E30 puo' dare un'altra competizione), modulo attivo, fase a 36 della coppa in memoria, e la
-- competizione scelta 0xFFFF (la schermata del campionato prende da sola la comp 4 o 6: segnale ad A2 come A1)
-- oppure un girone nativo della coppa (lo stato vero del dopo partita: consegna ad A2 della coppa e dell'id,
-- nessuna scrittura nel modello). Quando accende scrive una riga con i valori; con la chiave 2 o 3 e
-- l'interruttore spento una riga dice perche', con gli stessi valori (senza ripetere la stessa); con le altre
-- chiavi niente.
function m.on_after(ctx, event_id, registers)
    switch_cup, handover = nil, nil
    local third = registers and registers.r8             -- terzo argomento: r8b (0 dal menu, 1 dopo la partita)
    third = type(third) == "string" and #third >= 1 and third:byte(1) or nil
    if third == 0 then return end
    local mdl, root = career()
    if not mdl then return end
    local key = rd(mdl + KEY_OFF, 4)
    if not key then return end
    local cup = cup_by_key(u32(key, 0))
    if not cup then return end
    local chosen, sub = rd(mdl + CHOSEN_OFF, 2), rd(mdl + SUB_OFF, 4)
    local id = chosen and u16(chosen, 0)
    local values = string.format("%s (%s, terzo argomento %s)", cup_tag(cup), state_text(cup, chosen, sub),
        third and tostring(third) or "n/d")
    local why
    if tripped then
        why = "modulo in guasto"
        clear_flags()
    elseif paused() then
        why = "modulo in pausa"
        clear_flags()
    elseif not chosen then
        why = "competizione scelta non leggibile"
    elseif not sub then
        why = "sottoindice non leggibile"
    elseif u32(sub, 0) > 2 then
        why = "sottoindice oltre 2"
    else
        why = id ~= 0xFFFF and group_problem(mdl, root, cup, id) or nil
    end
    if not why then
        local plan, reason = m.prepare(cup)
        if plan then
            memory.write(after_switch, "\1")
            if id == 0xFFFF then
                switch_cup = cup
            else
                handover = { cup = cup, id = id }
            end
            last_after_note = nil
            log("[ucl36] classifica: dopo la partita schermata del campionato" .. values)
            return
        end
        why = reason
    end
    local text = "dopo la partita resta la schermata dei gironi" .. cup_tag(cup) .. ": " .. why
        .. values:sub(#cup_tag(cup) + 1)
    if text ~= last_after_note then
        log("[ucl36] classifica: " .. text)
        last_after_note = text
    end
end

-- Dopo una partita la schermata e' rimasta com'era nata: una riga con quello che si e' trovato, nessun guasto.
local function stays(hand, why)
    log(string.format("[ucl36] classifica: dopo la partita la schermata resta sul girone 0x%X: %s", hand.id, why))
end

-- A2: si apre la schermata del campionato (oggetto in RCX).
function m.on_open(ctx, event_id, registers)
    local obj = u64(registers.rcx, 0)
    local comp = rd(obj + OBJ_COMP_OFF, 2)
    local expected = switch_cup
    switch_cup = nil
    -- consegna di A5 (dopo una partita): vale per una sola apertura e solo per un oggetto che ha in +0xA8
    -- proprio l'id che A5 ha visto nel modello; in ogni altro caso una riga e la schermata resta com'e'
    local hand, redirect = handover, nil
    handover = nil
    if hand then
        if not comp then
            stays(hand, "oggetto non leggibile")
        elseif u16(comp, 0) ~= hand.id then
            stays(hand, string.format("competizione dell'oggetto 0x%X", u16(comp, 0)))
        elseif stopped() then
            stays(hand, tripped and "modulo in guasto" or "modulo in pausa")
            return
        else
            redirect = hand
        end
    end
    local cup = comp and cup_by_ko(u16(comp, 0)) or nil
    if redirect then cup = redirect.cup end
    -- la comp dell'oggetto sceglie la coppa (4 o 6); con il segnale di A1 deve essere quella
    -- della coppa per cui A1 ha acceso. Senza segnale lavora lo stesso: la tabella della comp 6
    -- e' sempre vuota per il gioco, quindi una schermata del campionato sulla comp 6 esiste solo
    -- per merito di A1 (e un segnale perso non deve lasciare lo schermo nero senza traccia)
    if cup == nil or (expected and cup ~= expected) then
        -- schermata del campionato creata per una coppa ma di un'altra competizione: schermo
        -- nero senza traccia, quindi una riga col valore (nessuna scrittura) e guasto
        if expected and comp then
            tripped = true
            clear_flags()
            note("schermata del campionato con competizione " .. u16(comp, 0) .. ", attesa " .. expected.ko
                .. ": il modulo non interviene piu' fino al riavvio")
        end
        return
    end
    if stopped() then return end
    -- una volta sola per schermata: le chiamate successive per lo stesso oggetto contano e basta
    local rewrite = false
    if not redirect and screen and screen.obj == obj and screen.cup == cup then
        screen.calls = screen.calls + 1
        if screen.calls >= TRIP_CALLS then
            trip(obj, screen.calls, cup)
            return
        end
        if not screen.written then
            -- la prima scrittura non e' riuscita: si riprova solo ogni RETRY_EVERY chiamate (la
            -- preparazione rilegge 7,7 MB di partite)
            if screen.calls % RETRY_EVERY ~= 0 then return end
        else
            local rows = game_rows(cup)
            if rows == TEAMS then return end
            if rows ~= 0 or screen.rewrote then return end
            screen.rewrote = true
            rewrite = true
        end
    else
        screen = { obj = obj, calls = 1, written = false, rewrote = false, cup = cup }
    end
    local plan, why = m.prepare(cup)
    if not plan then
        if redirect then
            -- niente contatore e niente guasto: l'oggetto resta sul girone, che ha la sua classifica a 4 righe
            screen = nil
            stays(redirect, why)
            return
        end
        note("schermata del campionato sulla comp " .. cup.ko .. ", classifica non scritta: " .. why)
        return
    end
    -- registro unico: se resta la tabella di un'altra schermata (chiusura persa) la si rimette
    -- prima di sovrascriverlo; non restore(), che azzera anche `screen`
    if ledger and ledger.addr ~= plan.addr and ledger_valid() then
        memory.write(ledger.addr, ledger.before)
        log("[ucl36] classifica: tabella della comp " .. ledger.cup.ko
            .. " rimessa com'era (si e' aperta un'altra schermata)")
    end
    ledger = { addr = plan.addr, before = plan.before, obj = obj, cup = cup }
    memory.write(plan.addr, plan.table)
    if redirect then
        -- le 36 righe ci sono: solo adesso l'oggetto passa alla comp 4 o 6 (2 byte, se c'e' ancora l'id atteso,
        -- e riletti). Da qui in poi e' una schermata come quelle del menu: contatore, riscrittura, A3.
        local now = rd(obj + OBJ_COMP_OFF, 2)
        local moved = now ~= nil and u16(now, 0) == redirect.id
        if moved then
            memory.write(obj + OBJ_COMP_OFF, pack(cup.ko, 2))
            now = rd(obj + OBJ_COMP_OFF, 2)
            moved = now ~= nil and u16(now, 0) == cup.ko
        end
        if not moved then
            memory.write(plan.addr, plan.before)
            ledger, screen = nil, nil
            stays(redirect, "la competizione dell'oggetto non risulta cambiata, tabella della comp " .. cup.ko
                .. " rimessa com'era")
            return
        end
        log(string.format("[ucl36] classifica: dopo la partita schermata del campionato portata dalla comp 0x%X alla comp %d",
            redirect.id, cup.ko))
    end
    screen.written = true
    last_note = nil
    if rewrite then
        log(string.format("[ucl36] classifica: tabella della comp %d trovata vuota alla chiamata %d per la stessa schermata: "
            .. "riscritta una volta (%d partite giocate)", cup.ko, screen.calls, plan.played))
        return
    end
    log(string.format("[ucl36] classifica: 36 righe scritte%s (%d partite giocate, prima la squadra %d%s), thread %d",
        cup.written, plan.played, plan.first, plan.order and "" or ", table.json assente o incompleto: ultimo criterio = id",
        tonumber(ffi.C.GetCurrentThreadId())))
end

-- A3: una schermata del campionato viene distrutta (oggetto in RCX).
function m.on_close(ctx, event_id, registers)
    local obj = u64(registers.rcx, 0)
    if screen and screen.obj == obj then screen = nil end    -- una schermata nuova allo stesso indirizzo riparte da zero
    if not ledger then return end
    if obj ~= ledger.obj then return end
    restore("chiusura, thread " .. tostring(tonumber(ffi.C.GetCurrentThreadId())))
end

-- Etichetta del menu (A4). Una riga per causa, come note().
local function label_note(text)
    if text ~= last_label_note then
        log("[ucl36] etichetta: " .. text .. ": la voce di menu resta quella del gioco")
        last_label_note = text
    end
end

-- Dove sta in memoria la stringa dell'id di testo `id`, cercata come fa il gioco (0x141497DD0):
-- gestore [0x143704DE8], categoria = id >> 16 nella std::map<u16, sezione*> di [gestore+0], indice =
-- id & 0xFFFF fra le voci da 12 byte della tabella della sezione, stringa = base + dword [voce+8].
-- Ritorna indirizzo, dimensione (con lo zero) e indirizzo della voce, oppure nil e il motivo. Solo letture protette, con
-- un tetto ai passi e alle voci: una struttura rovinata non puo' far girare il ciclo all'infinito.
local function text_entry(id)
    local mgr = pointer(TEXT_MGR_PTR)
    if not mgr then return nil, "gestore dei testi assente" end
    local head = pointer(mgr)
    if not head then return nil, "mappa dei testi assente" end
    local cat, idx = math.floor(id / 65536), id % 65536
    local node, sect = pointer(head + 8), nil        -- radice (padre della testa)
    for _ = 1, MAP_CAP do
        if not node or node == head then return nil, string.format("categoria 0x%X dei testi assente", cat) end
        local n = rd(node, 0x30)
        if not n then return nil, "nodo della mappa dei testi non leggibile" end
        if n:byte(0x19 + 1) ~= 0 then return nil, string.format("categoria 0x%X dei testi assente", cat) end
        local key = u16(n, 0x20)
        if key == cat then
            sect = u64(n, 0x28)
            break
        end
        node = u64(n, cat < key and 0 or 0x10)
        if node == 0 then node = nil end
    end
    if not sect then return nil, "mappa dei testi troppo profonda" end
    local base, tbl = pointer(sect), pointer(sect + 8)
    if not base or not tbl then return nil, "sezione dei testi 0x" .. string.format("%X", cat) .. " non leggibile" end
    local head_s = rd(tbl, 8)
    if not head_s then return nil, "tabella della sezione dei testi non leggibile" end
    local count = u32(head_s, 0)
    if count == 0 or count > SECTION_CAP then
        return nil, "sezione dei testi con " .. count .. " voci"
    end
    local ents = rd(tbl + 8, 12 * count)
    if not ents then return nil, "voci della sezione dei testi non leggibili" end
    for i = 0, count - 1 do
        if u16(ents, i * 12) == idx then
            return base + u32(ents, i * 12 + 8), u16(ents, i * 12 + 4), tbl + 8 + i * 12
        end
    end
    return nil, string.format("testo 0x%X assente dalla sezione", id)
end

-- Come text_entry, senza l'indirizzo della voce.
local function text_slot(id)
    local addr, size = text_entry(id)
    return addr, size
end

-- Caratteri di un testo UTF-8 (i byte 0x80..0xBF sono di continuazione).
local function utf8_chars(s)
    local n = 0
    for i = 1, #s do
        local b = s:byte(i)
        if b < 0x80 or b >= 0xC0 then n = n + 1 end
    end
    return n
end

-- La voce 0x44C0003 contiene la nostra etichetta nella lingua del gioco: true. Se contiene il testo nativo
-- di una lingua conosciuta la scrive e la rilegge. Altrimenti false e il motivo, senza scrivere.
-- Due strade. (1) L'etichetta entra nella voce: scritta sul posto, sopra il testo nativo (i byte dopo lo
-- zero restano quelli di prima). (2) Non entra: scritta all'inizio del testo di 0x44C0002, che nel file
-- precede 0x44C0003 senza buchi, e la voce 0x44C0003 (dimensione, caratteri, offset) viene portata li'.
-- La ricerca del gioco (0x1414996F0) ritorna base + offset della voce: da quel momento i due id danno
-- la nostra etichetta. Nessuno dei due e' usato dal gioco per PC (0x44C0002: DEDUZIONE, tre occorrenze
-- dei 4 byte solo nella sezione .impdata).
local function ensure_label_text()
    local addr, size, entry = text_entry(LABEL_ID)
    if not addr then return false, size end
    local unknown = string.format("il testo 0x44C0003 (%d byte) non e' quello di una lingua conosciuta "
        .. "(altra versione del gioco?)", size)
    if size > TEXT_CAP then return false, unknown end
    local current = rd(addr, size)
    if not current then return false, "il testo 0x44C0003 non e' leggibile" end
    for _, l in ipairs(LABELS) do
        local need = #l.label + 1
        if need <= #l.slot + 1 and size == #l.slot + 1 then
            local native = l.slot .. "\0"
            local ours = l.label .. "\0" .. native:sub(need + 1)
            if current == ours then return true end
            if current == native then
                memory.write(addr, l.label .. "\0")
                if rd(addr, size) ~= ours then return false, "il testo 0x44C0003 non risulta scritto" end
                log("[ucl36] etichetta: testo '" .. l.name .. "' (" .. l.lang .. ") scritto nella voce 0x44C0003")
                return true
            end
        end
    end
    local paddr, psize, pentry = text_entry(PREV_ID)
    if not paddr or psize > TEXT_CAP then return false, unknown end
    for _, l in ipairs(LABELS) do
        local need = #l.label + 1
        local ours = l.label .. "\0"
        if need > #l.slot + 1 then
            if addr == paddr then                    -- gia' fatto: la voce punta al testo di 0x44C0002
                if size == need and current == ours then return true end
            elseif size == #l.slot + 1 and psize == #l.prev + 1 and paddr + psize == addr and need <= psize + size
                and current == l.slot .. "\0" and rd(paddr, psize) == l.prev .. "\0" then
                local prev_entry = rd(pentry, 12)
                if not prev_entry then return false, "la voce 0x44C0002 non e' leggibile" end
                memory.write(paddr, ours)
                if rd(paddr, need) ~= ours then return false, "il testo 0x44C0002 non risulta scritto" end
                memory.write(entry + 4, pack(need, 2) .. pack(utf8_chars(l.label), 2) .. prev_entry:sub(9, 12))
                local now, now_size = text_entry(LABEL_ID)
                if now ~= paddr or now_size ~= need then return false, "la voce 0x44C0003 non risulta spostata" end
                log("[ucl36] etichetta: testo '" .. l.name .. "' (" .. l.lang .. ") scritto nello spazio di 0x44C0002, "
                    .. "voce 0x44C0003 portata li'")
                return true
            end
        end
    end
    return false, unknown
end

-- I due byte dell'intestazione della giornata: 1 solo con il modulo attivo, la fase a 36 della coppa in memoria
-- (o i suoi gironi non ancora sorteggiati: la fase a 36 arriva al sorteggio) e "Fase campionato" nella voce
-- 0x44C0003. `recheck` rifa' il controllo delle fasi, nella forma piu' leggera
-- che risponde alla domanda: una sola lettura dei 7,7 MB di partite per le due coppe, le 144 partite a 36
-- (league_state) e il record dei risultati della comp a eliminazione (find_table); niente classifica, niente
-- table.json, niente tabella (A1 e A4, che decidono una schermata, fanno la preparazione intera). Senza
-- `recheck` vale l'ultimo esito. Il testo si ricontrolla sempre, e solo se almeno una coppa lo usa: se il gioco
-- ricarica le lingue la voce torna "Scheda giocatore". Ritorna true se il controllo delle fasi e' stato rifatto
-- (modulo fermo, pezzi spenti o nessuna carriera: no, e resta da fare).
local function refresh_flags(recheck)
    if not flag_addr or stopped() then return false end
    local mdl, root = career()
    if not mdl then return false end
    local events = recheck and rd(mdl + EVENT_OFF, EVENT_SIZE * EVENT_COUNT)
    local any = false
    for _, cup in ipairs(CUP_LIST) do
        if recheck then
            local state, _, n = nil, nil, nil
            if events then state, _, n = m.league_state(events, cup) end
            -- b2-7: dalla pulizia di luglio al sorteggio in memoria non c'e' nessuna partita dei gironi della
            -- coppa. La fase a 36 arriva al sorteggio e l'intestazione la annuncia gia'. Con i gironi del gioco
            -- sorteggiati (partite con le squadre, ma non le nostre 144 a 36) resta "Fase a gironi".
            pending[cup] = events ~= nil and state == nil and n == 0
            phase[cup] = (state ~= nil and find_table(root, cup) ~= nil) or pending[cup]
        end
        any = any or phase[cup] == true
    end
    if not any then
        clear_flags()
        return recheck
    end
    local ok, why = ensure_label_text()
    if not ok then
        clear_flags()
        if why ~= last_flag_note then
            log("[ucl36] etichetta: " .. why .. ": l'intestazione della giornata resta quella del gioco")
            last_flag_note = why
        end
        return recheck
    end
    last_flag_note = nil
    for _, cup in ipairs(CUP_LIST) do set_flag(cup, phase[cup] == true) end
    return recheck
end

-- A4: si apre il sottomenu della competizione (gira prima che le voci siano riempite). Con la chiave 2 o 3
-- (Champions, Europa League): se il modulo e' attivo e la fase a 36 di quella coppa e' in memoria (lo stesso
-- controllo di A1) il dword "nome della fase" della coppa diventa 0x44C0003 ("Fase campionato"), altrimenti
-- torna 0x3A20011 ("Fase a gironi"). Valori attesi controllati prima di ogni scrittura; il dword non si
-- scrive mai se il testo non e' al suo posto.
function m.on_menu(ctx, event_id, registers)
    local mdl = career()
    if not mdl then return end
    local key = rd(mdl + KEY_OFF, 4)
    if not key then return end
    local cup = cup_by_key(u32(key, 0))
    if not cup then return end
    local want, why = false, nil
    if tripped then
        why = "modulo in guasto"
        clear_flags()
    elseif paused() then
        why = "modulo in pausa"
        clear_flags()
    else
        local plan, reason = m.prepare(cup)
        want, why = plan ~= nil, reason
        -- l'intestazione della giornata segue lo stesso esito: spenta subito, accesa sotto quando il testo e' confermato
        -- prima del sorteggio la voce di menu resta quella del gioco (porta ai gironi vuoti), l'intestazione no
        phase[cup] = want or pending[cup] == true
        if not phase[cup] then set_flag(cup, false) end
    end
    local raw = rd(cup.stage, 4)
    if not raw then
        label_note(cup.name .. ": nome della fase non leggibile")
        return
    end
    local current = u32(raw, 0)
    if current ~= NATIVE_ID and current ~= LABEL_ID then
        label_note(string.format("%s: nome della fase 0x%X inatteso", cup.name, current))
        return
    end
    if want then
        local ok, why = ensure_label_text()
        if not ok then
            -- il dword puo' valere 0x44C0003 solo finche' la voce contiene il nostro testo
            if current == LABEL_ID then memory.write(cup.stage, p32(NATIVE_ID)) end
            clear_flags()                        -- il testo e' uno solo per le due coppe
            label_note(why)
            return
        end
        set_flag(cup, true)
        last_label_note = nil
        if current ~= LABEL_ID then
            memory.write(cup.stage, p32(LABEL_ID))
            log("[ucl36] etichetta: " .. cup.name .. " con la fase a 36 in memoria: 'Fase campionato'")
        end
    elseif current == LABEL_ID then
        memory.write(cup.stage, p32(NATIVE_ID))
        last_label_note = nil
        log("[ucl36] etichetta: " .. cup.name .. " senza fase a 36 attiva: rimessa 'Fase a gironi'")
    else
        -- resta quella nativa: una riga (senza ripetizioni) col motivo, per distinguere "l'aggancio scatta
        -- ma la fase a 36 non c'e'" da "l'aggancio non scatta"
        local text = cup.name .. ": resta 'Fase a gironi' (" .. why .. ")"
        if text ~= last_label_note then
            log("[ucl36] etichetta: " .. text)
            last_label_note = text
        end
    end
end

-- Tabella della comp 4 o 6 con 36 righe e nessuna schermata nostra aperta: e' rimasta
-- piena (chiusura non passata da A3) e non deve finire in un salvataggio. Il
-- gioco, da solo, la tiene sempre a zero righe.
local function sweep()
    local mdl, root = model()
    if not mdl then return end
    for _, cup in ipairs(CUP_LIST) do
        for _, addr in ipairs(season_tables(root, cup)) do
            local current = rd(addr, TABLE_SIZE)
            if current and u32(current, COUNT_OFF) == TEAMS then
                memory.write(addr, m.emptied(current))
                log("[ucl36] classifica: tabella della comp " .. cup.ko .. " rimasta piena: svuotata")
            end
        end
    end
end

-- Barra del calendario della ML (entry = una partita): controllo ogni 2 secondi. Nello stesso giro i due byte
-- dell'intestazione della giornata: il testo ogni volta, la fase a 36 in memoria ogni PHASE_EVERY.
function m.calendar(ctx, name, stadium, entry)
    if entry and not ledger then
        local now = m.tick()
        if now >= next_sweep then
            next_sweep = now + 2000
            sweep()
            if refresh_flags(now >= next_phase) then next_phase = now + PHASE_EVERY end
        end
    end
    return nil
end

-- Il gioco prepara una partita: nessuna schermata della classifica puo' essere aperta.
function m.match_setup(ctx)
    career()                                 -- una partita fuori dalla carriera: l'intestazione della giornata si spegne
    screen, handover = nil, nil
    if ledger then restore("partita in preparazione") end
end

-- Codice macchina (funzioni pure, provate nei test).
function m.trigger(evt_rbx, event_id)
    return "\x53\x51"                                    -- push rbx ; push rcx
        .. "\x48\xBB" .. p64(evt_rbx)                    -- mov rbx, <gestore degli eventi di Sider>
        .. "\x66\xB9" .. pack(event_id, 2)               -- mov cx, <evento>
        .. "\xFF\xD3"                                    -- call rbx
        .. "\x48\x83\xC4\x10"                            -- add rsp, 0x10
end

local function jmp_abs(addr)
    return "\xFF\x25\x00\x00\x00\x00" .. p64(addr)       -- jmp [rip+0] ; <indirizzo>
end

function m.patch(cave, size)
    return jmp_abs(cave) .. string.rep("\x90", size - 14)
end

-- A2 e A3: evento, byte originali, ritorno.
function m.entry_cave(trigger, site)
    return trigger .. site.original .. jmp_abs(site.addr + #site.original)
end

-- A1 e A5: azzera l'interruttore, evento, poi schermata del campionato (site.target) se e' acceso. Il salto
-- lascia gli argomenti come sono: rax all'ingresso di una funzione e' libero.
function m.create_cave(trigger, site, switch)
    return "\x48\xB8" .. p64(switch) .. "\xC6\x00\x00"   -- mov rax, <interruttore> ; mov byte [rax], 0
        .. trigger
        .. "\x48\xB8" .. p64(switch) .. "\x80\x38\x00"   -- mov rax, <interruttore> ; cmp byte [rax], 0
        .. "\x74\x0C"                                    -- je <originale>
        .. "\x48\xB8" .. p64(site.target) .. "\xFF\xE0"  -- mov rax, <creatore del campionato> ; jmp rax
        .. site.original .. jmp_abs(site.addr + #site.original)
end

-- Intestazione della giornata: quello che faceva il blocco del gioco (edx = id del testo, rcx = dove metterlo),
-- poi 0x44C0003 al posto di 0x3A20011 se la chiave e' 2 o 3 e il byte di quella coppa non e' zero. Nessun
-- evento Lua; rax e' libero (prima e dopo il blocco c'e' una call), i flag non servono a chi viene dopo.
function m.label_cave(site, ucl_flag, uel_flag)
    local set = "\xBA" .. p32(LABEL_ID)                               -- mov edx, 0x44C0003
    local function check(flag)
        return "\x48\xB8" .. p64(flag) .. "\x80\x38\x00"             -- mov rax, <byte della coppa> ; cmp byte [rax], 0
    end
    local uel = site.cmp .. "\x03" .. "\x75\x14"                      -- altra: cmp <chiave>, 3 ; jne fine
        .. check(uel_flag) .. "\x74\x05" .. set                       -- je fine ; mov edx, 0x44C0003
    local ucl = check(ucl_flag) .. "\x74" .. string.char(7 + #uel)    -- je fine
        .. set .. "\xEB" .. string.char(#uel)                         -- mov edx, 0x44C0003 ; jmp fine
    local tail = site.cmp .. "\x02" .. "\x75" .. string.char(#ucl)    -- cmp <chiave>, 2 ; jne altra
        .. ucl .. uel
    local o = site.original
    if site.two_exits then
        -- ramo "testi corti" (id 0x510028): dritto all'uscita, senza passare dal nostro controllo; l'altro ramo
        -- (mov edx, 0x3A20011) prosegue nel controllo invece di saltare all'uscita
        return o:sub(1, 20) .. "\xEB" .. string.char(5 + #tail) .. o:sub(23, 27) .. tail .. jmp_abs(site.exit)
    end
    return o .. tail .. jmp_abs(site.exit)                            -- fine: jmp <uscita del blocco>
end

m.sites = SITES
m.label_sites = LABEL_SITES
m.marker = MARKER
m.find_table = find_table              -- esposte per i test
m.season_tables = season_tables
m.cups = CUPS
m.text_slot = text_slot

-- Un nostro aggancio rimasto da prima (moduli ricaricati): salto a un pezzo di
-- codice che ha il marcatore nei 16 byte precedenti.
local function stale_hook(current)
    if not current or current:sub(1, 6) ~= "\xFF\x25\x00\x00\x00\x00" then return false end
    return rd(u64(current, 6) - #MARKER, #MARKER) == MARKER
end

local function adriel_table_loaded(ini_path)
    local f = io.open(ini_path, "r")
    if not f then return false end
    local text = f:read("*a")
    f:close()
    for line in text:gmatch("[^\r\n]+") do
        if line:match('^%s*lua%.module%s*=%s*"ucl_schedule_probe%.lua"') then return true end
    end
    return false
end

function m.init(ctx)
    if ffi == nil then error("ucl36_table: servono le estensioni LuaJIT (luajit.ext.enabled)") end
    local sider_dir = ctx.sider_dir:gsub("[\\/]+$", "")
    runtime_dir = sider_dir .. "\\content\\ucl36"
    local stale, unknown = {}, nil
    for _, name in ipairs(SITE_ORDER) do
        local site = SITES[name]
        local current = rd(site.addr, #site.original)
        if current ~= site.original then
            if stale_hook(current) then
                stale[#stale + 1] = site
            else
                unknown = unknown or string.format("%s (0x%X)", name, site.addr)
            end
        end
    end
    -- il quarto e il quinto aggancio sono extra: byte inattesi li spengono da soli, gli altri non ne risentono
    local extra_ok, extra_why = {}, {}
    for _, name in ipairs(EXTRA_ORDER) do
        local site = SITES[name]
        local now = rd(site.addr, #site.original)
        extra_ok[name] = now == site.original
        extra_why[name] = string.format("byte inattesi nel punto %s (0x%X)", name, site.addr)
        if not extra_ok[name] and stale_hook(now) then
            stale[#stale + 1] = site
            extra_ok[name] = true
        end
    end
    -- lo stesso per i due pezzi dell'intestazione della giornata, uno per uno
    local label_ok, labels = {}, 0
    for i, site in ipairs(LABEL_SITES) do
        local now = rd(site.addr, #site.original)
        label_ok[i] = now == site.original
        if not label_ok[i] and stale_hook(now) then
            stale[#stale + 1] = site
            label_ok[i] = true
        end
        if label_ok[i] then labels = labels + 1 end
    end
    -- i nostri agganci rimasti da prima si tolgono comunque, anche se poi si rinuncia: senza il modulo che
    -- li serve resterebbero installati con gli interruttori e i byte dell'intestazione fermi
    for _, site in ipairs(stale) do memory.write(site.addr, site.original) end
    if adriel_table_loaded(sider_dir .. "\\sider.ini") then
        log("[ucl36] classifica: ucl_schedule_probe.lua di Adriel e' in sider.ini: non intervengo")
        return
    end
    if not ctx.custom_evt_rbx or not ctx.get_event_id then
        log("[ucl36] classifica: questo Sider non ha gli eventi custom: non intervengo")
        return
    end
    if unknown then
        log("[ucl36] classifica: byte inattesi nel punto " .. unknown .. ": non intervengo")
        return
    end
    -- allocate_codecave restituisce un puntatore ffi; custom_evt_rbx puo' essere un
    -- numero o un puntatore: qui servono numeri
    local cave = tonumber(ffi.cast("uintptr_t", memory.allocate_codecave(1024)))
    local evt_rbx = tonumber(ffi.cast("uintptr_t", ctx.custom_evt_rbx))
    -- i primi 16 byte sono dati nostri, a zero: interruttore di A1, interruttore di A5, i due byte dell'intestazione
    switch_addr, after_switch = cave, cave + 1
    local ucl_flag, uel_flag = cave + 2, cave + 3
    local parts, entry, pos = { string.rep("\0", 16) }, {}, 16
    for _, name in ipairs(SITE_ORDER) do
        local site = SITES[name]
        local trigger = m.trigger(evt_rbx, ctx.get_event_id(site.event))
        local code = m.entry_cave(trigger, site)
        if name == "create" then code = m.create_cave(trigger, site, switch_addr) end
        parts[#parts + 1] = MARKER .. code
        entry[name] = cave + pos + #MARKER
        pos = pos + #MARKER + #code
    end
    local hooks = #SITE_ORDER
    for _, name in ipairs(EXTRA_ORDER) do
        if extra_ok[name] then
            -- l'id dell'evento di un aggancio extra si controlla: se non e' un numero quell'aggancio resta spento
            -- e gli altri si installano lo stesso
            local site = SITES[name]
            local event = ctx.get_event_id(site.event)
            if type(event) ~= "number" then
                extra_ok[name], extra_why[name] = false, EXTRA_TEXT[name][2]
            else
                local trigger = m.trigger(evt_rbx, event)
                local code = m.entry_cave(trigger, site)
                if name == "after" then code = m.create_cave(trigger, site, after_switch) end
                parts[#parts + 1] = MARKER .. code
                entry[name] = cave + pos + #MARKER
                pos = pos + #MARKER + #code
                hooks = hooks + 1
            end
        end
    end
    local label_entry = {}
    for i, site in ipairs(LABEL_SITES) do
        if label_ok[i] then
            local code = m.label_cave(site, ucl_flag, uel_flag)
            parts[#parts + 1] = MARKER .. code
            label_entry[i] = cave + pos + #MARKER
            pos = pos + #MARKER + #code
        end
    end
    memory.write(cave, table.concat(parts))
    flag_addr = nil
    if labels > 0 then flag_addr = { [CUPS.ucl] = ucl_flag, [CUPS.uel] = uel_flag } end
    ctx.register(SITES.create.event, m.on_create)
    ctx.register(SITES.open.event, m.on_open)
    ctx.register(SITES.close.event, m.on_close)
    if extra_ok.menu then ctx.register(SITES.menu.event, m.on_menu) end
    if extra_ok.after then ctx.register(SITES.after.event, m.on_after) end
    ctx.register("get_stadium_name", m.calendar)
    ctx.register("set_teams", m.match_setup)
    ctx.register("after_set_conditions", m.match_setup)
    for _, name in ipairs(SITE_ORDER) do
        memory.write(SITES[name].addr, m.patch(entry[name], #SITES[name].original))
    end
    for _, name in ipairs(EXTRA_ORDER) do
        if extra_ok[name] then
            memory.write(SITES[name].addr, m.patch(entry[name], #SITES[name].original))
        else
            log("[ucl36] " .. EXTRA_TEXT[name][1] .. ": " .. extra_why[name] .. ": " .. EXTRA_TEXT[name][3])
        end
    end
    for i, site in ipairs(LABEL_SITES) do
        if label_ok[i] then
            memory.write(site.addr, m.patch(label_entry[i], #site.original))
        else
            log(string.format("[ucl36] etichetta: byte inattesi nel punto calendario %d (0x%X): li' l'intestazione "
                .. "della giornata resta quella del gioco", i, site.addr))
        end
    end
    sweep()
    log(string.format("[ucl36] ucl36_table %s attivo: %d agganci, etichetta del calendario in %d punti su 2, codice a 0x%X",
        m.version, hooks, labels, cave))
    refresh_flags(true)                      -- con una carriera gia' in memoria (moduli ricaricati) i byte partono giusti
end

return m
