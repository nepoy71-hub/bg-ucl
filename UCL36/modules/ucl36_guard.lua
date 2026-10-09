-- UCL36 B1: lancia il worker Python (fase a campionato a 36, riparazione del
-- tabellone) quando la ML carica calendario, classifica o menu principale.
-- Un avvio alla volta, mai durante una partita; fuori dai blocchi SYNC al
-- massimo uno ogni 30 secondi.
-- SYNC (b1-7): il worker scrive in state.json la prossima finestra con lavoro
-- da fare ("sync"); al ritorno al calendario in un giorno della finestra la
-- guardia lancia il worker e ASPETTA che finisca (il gioco resta fermo qualche
-- secondo), cosi' gli stadi arrivano anche in simulazione continua. In un
-- blocco gli avvii sono al massimo 3, uno dopo l'altro, in 30 secondi in tutto.
-- Blocca anche quando la finestra nota e' gia' passata o e' stata calcolata in
-- un giorno successivo a oggi (salvataggio ricaricato): serve a farsi dire la
-- finestra nuova. Resta quieta solo tra il giorno del calcolo e l'inizio.
-- Nessuna logica di calcio.
local m = { version = "b1-7" }
local IMAGE_BASE, ROOT_RVA, MODEL_PTR_OFF = 0x140000000, 0x3705E10, 0x48
local DAY_OFF = 0x16038A8 + 0x3F174       -- giorno corrente (u16), poi l'anno (u16)
local MEM_COMMIT, PAGE_NOACCESS, PAGE_GUARD = 0x1000, 0x01, 0x100
local SEASON_START, YEAR_DAYS = 181, 365  -- 1 luglio, righe del calendario
local BLOCK_MS, MAX_RUNS = 30000, 3       -- attesa massima e avvii per blocco
local worker = nil
local next_check = 0
local last_status = nil
local in_match = false
local last_setup = nil                    -- tick dell'ultima preparazione di partita
local sync = nil                          -- ultima finestra detta dal worker
local last_block = nil                    -- "anno|giorno" dell'ultimo blocco
local runtime_dir, python

if ffi ~= nil then
    ffi.cdef[[
        typedef struct {
            unsigned long cb; char* lpReserved; char* lpDesktop; char* lpTitle;
            unsigned long dwX; unsigned long dwY; unsigned long dwXSize;
            unsigned long dwYSize; unsigned long dwXCountChars;
            unsigned long dwYCountChars; unsigned long dwFillAttribute;
            unsigned long dwFlags; unsigned short wShowWindow;
            unsigned short cbReserved2; unsigned char* lpReserved2;
            void* hStdInput; void* hStdOutput; void* hStdError;
        } UCL36_STARTUPINFOA;
        typedef struct {
            void* hProcess; void* hThread; unsigned long dwProcessId;
            unsigned long dwThreadId;
        } UCL36_PROCESS_INFORMATION;
        typedef struct {
            void* BaseAddress; void* AllocationBase; unsigned long AllocationProtect;
            unsigned short PartitionId; size_t RegionSize; unsigned long State;
            unsigned long Protect; unsigned long Type;
        } UCL36_MBI;
        void* GetModuleHandleA(const char* lpModuleName);
        void* GetProcAddress(void* hModule, const char* lpProcName);
        int CloseHandle(void* hObject);
        unsigned long GetLastError(void);
        unsigned long GetCurrentProcessId(void);
        unsigned long long GetTickCount64(void);
        int GetExitCodeProcess(void* hProcess, unsigned long* lpExitCode);
        size_t UCL36_VirtualQuery(const void* lpAddress, UCL36_MBI* lpBuffer, size_t dwLength)
            __asm__("VirtualQuery");
        unsigned long UCL36_WaitForSingleObject(void* hHandle, unsigned long dwMilliseconds)
            __asm__("WaitForSingleObject");
    ]]
end

-- Nomi privati (UCL36_...) legati con __asm__ alle funzioni di kernel32: la
-- libreria "memory" di Sider dichiara gia' VirtualQuery e
-- MEMORY_BASIC_INFORMATION nello spazio ffi condiviso, e una seconda
-- dichiarazione con tipi diversi farebbe fallire ogni hook (Sider non ha pcall).
local function readable(addr, size)
    local mbi = ffi.new("UCL36_MBI[1]")
    if ffi.C.UCL36_VirtualQuery(ffi.cast("void*", addr), mbi, ffi.sizeof(mbi[0])) == 0 then return false end
    local r = mbi[0]
    if r.State ~= MEM_COMMIT then return false end
    if bit.band(r.Protect, PAGE_NOACCESS) ~= 0 or bit.band(r.Protect, PAGE_GUARD) ~= 0 then return false end
    local base = tonumber(ffi.cast("uintptr_t", r.BaseAddress))
    return addr + size <= base + tonumber(r.RegionSize)
end

function m.peek_u64(addr)
    if not readable(addr, 8) then return nil end
    return tonumber(ffi.cast("uint64_t*", addr)[0])
end

function m.peek_u16(addr)
    if not readable(addr, 2) then return nil end
    return tonumber(ffi.cast("uint16_t*", addr)[0])
end

-- Giorno e anno della ML dalla memoria del gioco; nil nei menu (anno 0), senza
-- ML caricata o se un puntatore non si legge.
function m.read_day()
    local root = m.peek_u64(IMAGE_BASE + ROOT_RVA)
    if not root or root == 0 then return nil end
    local model = m.peek_u64(root + MODEL_PTR_OFF)
    if not model or model == 0 then return nil end
    local day = m.peek_u16(model + DAY_OFF)
    local year = m.peek_u16(model + DAY_OFF + 2)
    if not day or not year or year == 0 or day >= YEAR_DAYS then return nil end
    return day, year
end

local function season_order(day)
    return (day - SEASON_START) % YEAR_DAYS
end

-- Giorno assoluto, come sync.absolute del worker: stagione * 365 + posto nella
-- stagione (la stagione e' l'anno in cui comincia, il 1 luglio).
local function absolute(day, year)
    local season = year
    if day < SEASON_START then season = year - 1 end
    return season * YEAR_DAYS + season_order(day)
end

-- C'e' da bloccare oggi? nil = no (nessuna finestra nota, oppure finestra
-- futura calcolata nel passato: la guardia resta quieta). Se no la fase per il
-- log: "<fase>" dentro la finestra, "<fase> scaduta" se la finestra e' passata
-- o se oggi viene prima del giorno del calcolo (salvataggio piu' vecchio
-- ricaricato, altra carriera): il blocco serve a farsi dire la finestra nuova.
local function due(day, year)
    if not sync then return nil end
    local t = absolute(day, year)
    if sync.start <= t and t <= sync.stop then return sync.stage end
    if sync.from <= t and t < sync.start then return nil end
    return sync.stage .. " scaduta"
end

-- Legge state.json: registra lo stato quando cambia, aggiorna `sync` se il
-- worker l'ha scritto (se no resta l'ultimo noto). Restituisce lo stato e se
-- questo file aveva un `sync` utilizzabile.
local function report()
    local f = io.open(runtime_dir .. "\\state.json", "r")
    if not f then
        log("[ucl36] nessuno stato scritto dal worker")
        return nil
    end
    local text = f:read("*a")
    f:close()
    local status = text:match('"status"%s*:%s*"([^"]+)"')
    if not status then
        log("[ucl36] nessuno stato scritto dal worker")
        return nil
    end
    -- from/start/end sono giorni assoluti (vedi absolute); uno state.json di
    -- prima, senza quei tre numeri, vale come senza sync
    local fresh = false
    local block = text:match('"sync"%s*:%s*(%b{})')
    if block then
        local first = tonumber(block:match('"first"%s*:%s*(%d+)'))
        local last = tonumber(block:match('"last"%s*:%s*(%d+)'))
        local from = tonumber(block:match('"from"%s*:%s*(%d+)'))
        local start = tonumber(block:match('"start"%s*:%s*(%d+)'))
        local stop = tonumber(block:match('"end"%s*:%s*(%d+)'))
        if first and last and first < YEAR_DAYS and last < YEAR_DAYS
           and from and start and stop and from <= stop and start <= stop then
            sync = { from = from, start = start, stop = stop,
                     stage = block:match('"stage"%s*:%s*"([^"]*)"') or "?",
                     again = block:match('"again"%s*:%s*true') ~= nil }
            fresh = true
        end
    end
    -- il motivo puo' contenere \" (messaggi d'eccezione): si legge fino alle
    -- prime virgolette non precedute da \
    local reason = ""
    local _, start = text:find('"reason"%s*:%s*"')
    if start then
        local i = start + 1
        while i <= #text do
            local c = text:sub(i, i)
            if c == "\\" then
                reason = reason .. text:sub(i + 1, i + 1)
                i = i + 2
            elseif c == '"' then
                break
            else
                reason = reason .. c
                i = i + 1
            end
        end
    end
    if status ~= last_status then
        log("[ucl36] " .. status .. ": " .. reason)
        last_status = status
    end
    return status, fresh
end

-- Raccoglie il worker se e' uscito. Restituisce: finito (true anche senza
-- worker), lo stato letto (nil se non c'era nulla da raccogliere) e se lo
-- stato letto portava un `sync` utilizzabile.
local function collect()
    if worker == nil then return true, nil, false end
    local code = ffi.new("unsigned long[1]")
    if ffi.C.GetExitCodeProcess(worker, code) ~= 0 and code[0] == 259 then return false, nil, false end
    local exit_code = code[0]
    ffi.C.CloseHandle(worker)
    worker = nil
    if exit_code ~= 0 then
        log("[ucl36] worker uscito con codice " .. tostring(exit_code) .. " (vedi content\\ucl36\\ucl36.log)")
    end
    local status, fresh = report()
    return true, status or "nessuno stato", fresh == true
end

-- Lancia il worker; true se e' partito.
local function launch()
    local reset = io.open(runtime_dir .. "\\state.json", "w")
    if reset then
        reset:write("{}")
        reset:close()
    end
    local command = '"' .. python .. '" -m ucl36.worker --pid ' .. tostring(ffi.C.GetCurrentProcessId()) ..
        ' --apply --output "' .. runtime_dir .. '\\state.json" --log "' .. runtime_dir .. '\\ucl36.log"' ..
        ' --data "' .. runtime_dir .. '\\data\\real_2026_27.json" --backup-dir "' .. runtime_dir .. '\\backup"' ..
        ' --sider-ini "' .. runtime_dir .. '\\..\\..\\sider.ini"' .. ' --uel36'
    local buffer = ffi.new("char[?]", #command + 1, command)
    local startup = ffi.new("UCL36_STARTUPINFOA[1]")
    local process = ffi.new("UCL36_PROCESS_INFORMATION[1]")
    startup[0].cb = ffi.sizeof(startup[0])
    local kernel = ffi.C.GetModuleHandleA("kernel32.dll")
    local entry = kernel ~= nil and ffi.C.GetProcAddress(kernel, "CreateProcessA") or nil
    if entry == nil then
        log("[ucl36] CreateProcessA non disponibile")
        return false
    end
    local create_process = ffi.cast(
        "int(*)(const char*,char*,void*,void*,int,unsigned long,void*,const char*,void*,void*)", entry)
    if create_process(python, buffer, nil, nil, 0, 0x08000000, nil, runtime_dir,
        ffi.cast("void*", startup), ffi.cast("void*", process)) == 0 then
        log("[ucl36] avvio del worker fallito: " .. tostring(ffi.C.GetLastError()))
        return false
    end
    ffi.C.CloseHandle(process[0].hThread)
    worker = process[0].hProcess
    return true
end

local function tick()
    if not collect() then return end
    if in_match then return end
    local now = tonumber(ffi.C.GetTickCount64())
    if now < next_check then return end
    next_check = now + 30000
    launch()
end

-- Blocco mirato (SYNC §5.2): lancia il worker e aspetta che finisca, al massimo
-- BLOCK_MS in tutto. Rilancia subito, fino a MAX_RUNS avvii, se il worker dice
-- "again" (la Champions ha scritto e tocca alla UEL, scrittura rifiutata,
-- tabella dei risultati mancante) o se il suo stato non porta un `sync`
-- (worker senza cattura: il gioco stava avanzando). Oltre il tempo smette di
-- aspettare: il worker prosegue da solo e lo raccoglie il prossimo tick.
-- Un worker gia' in corso si aspetta e poi il blocco fa comunque almeno un avvio
-- suo, perche' quel worker e' partito in un giorno precedente.
-- `stage` e' la fase per il log (vedi due); `from_match` = questo ritorno al
-- calendario chiude una partita. La prima riga del log, scritta PRIMA di
-- lanciare, dice quanto e' lontana l'ultima preparazione di partita: un blocco
-- arrivato mentre il gioco prepara una partita si vede li' (pochi ms).
local function block(day, stage, from_match)
    local t0 = tonumber(ffi.C.GetTickCount64())
    local setup = "nessuna preparazione di partita in questa sessione"
    if last_setup then
        setup = string.format("ultima preparazione di partita %d ms fa", t0 - last_setup)
    end
    log(string.format("[ucl36] blocco al giorno %d: ritorno da una partita %s, %s",
        day, from_match and "si" or "no", setup))
    local runs, seen = 0, {}
    local outcome = nil
    while true do
        if worker == nil then
            if runs >= MAX_RUNS then break end
            if not launch() then
                outcome = "avvio fallito"
                break
            end
            runs = runs + 1
        end
        local left = BLOCK_MS - (tonumber(ffi.C.GetTickCount64()) - t0)
        local waited = 258                    -- WAIT_TIMEOUT
        if left > 0 then waited = tonumber(ffi.C.UCL36_WaitForSingleObject(worker, left)) end
        if waited == 258 then
            outcome = "oltre " .. tostring(BLOCK_MS / 1000) .. " s, il worker prosegue da solo"
            break
        end
        if waited ~= 0 then                   -- es. WAIT_FAILED: non e' un tempo scaduto
            outcome = "attesa fallita (codice " .. tostring(waited) .. ")"
            break
        end
        local finished, status, fresh = collect()
        if not finished then                  -- attesa riuscita ma codice d'uscita 259
            outcome = "il worker non risulta finito, prosegue da solo"
            break
        end
        seen[#seen + 1] = status
        if runs > 0 and fresh and not sync.again then break end
    end
    local now = tonumber(ffi.C.GetTickCount64())
    next_check = now + 30000
    local text = table.concat(seen, ", ")
    if outcome then text = (text ~= "" and (text .. "; ") or "") .. outcome end
    log(string.format("[ucl36] blocco al giorno %d (%s): %s in %.1f s", day, stage, text, (now - t0) / 1000))
end

function m.data_ready(ctx, filename, data, len, total_size, offset)
    local name = string.lower(filename or "")
    if offset + len >= total_size and
       (name:match("\\schedule%.bin$") or name:match("\\rankinggroupleaguepes%.bin$")
        or name:match("\\modemainmenuml%.bin$")) then
        tick()
    end
end

-- Mentre il gioco prepara o gioca una partita il worker non parte:
-- set_teams / after_set_conditions lo mettono in pausa. In ML context_reset
-- non scatta a fine partita (provato il 2026-09-26): il segnale di ritorno e'
-- la barra del calendario (get_stadium_name con entry, che durante la
-- partita non arriva). Si riparte 15 s dopo: il gioco sta scaricando la partita.
local function resume()
    if not in_match then return end
    log("[ucl36] ritorno al calendario: worker di nuovo attivo tra 15 s")
    in_match = false
    next_check = math.max(next_check, tonumber(ffi.C.GetTickCount64()) + 15000)
end

function m.match_setup(ctx)
    if not in_match then log("[ucl36] partita in preparazione: worker in pausa") end
    in_match = true
    last_setup = tonumber(ffi.C.GetTickCount64())
end

function m.context_reset(ctx)
    resume()
end

-- livecpk_data_ready scatta solo per i file serviti da una cartella livecpk
-- (Adriel ha i suoi in livecpk\UCL32, spenta dal profilo B1): la barra del
-- calendario della ML chiede lo stadio di ogni partita (entry = la partita),
-- e quello e' l'aggancio che scatta davvero. Restituisce nil: il nome dello
-- stadio lo decidono gli altri moduli.
-- Quando c'e' da bloccare (vedi due: giorno della finestra `sync`, finestra
-- passata, giorno precedente al calcolo), una volta per giorno, il worker parte
-- subito e la guardia lo aspetta: e' l'unico momento in cui il gioco e' fermo
-- sul calendario anche in simulazione continua (ricerca SYNC R1).
function m.get_stadium_name(ctx, name, stadium, entry)
    if entry then
        local from_match = in_match
        resume()
        local day, year = m.read_day()
        local key = day and (tostring(year) .. "|" .. tostring(day))
        local stage = nil
        if day and key ~= last_block then stage = due(day, year) end
        if stage then
            last_block = key
            block(day, stage, from_match)
        else
            tick()
        end
    end
    return nil
end

function m.init(ctx)
    if ffi == nil then error("ucl36_guard: servono le estensioni LuaJIT (luajit.ext.enabled)") end
    runtime_dir = ctx.sider_dir:gsub("[\\/]+$", "") .. "\\content\\ucl36"
    local config = io.open(runtime_dir .. "\\python.txt", "r")
    if not config then error("ucl36_guard: manca content\\ucl36\\python.txt") end
    python = config:read("*l")
    config:close()
    local exe = io.open(python, "rb")
    if not exe then error("ucl36_guard: Python non trovato: " .. tostring(python)) end
    exe:close()
    ctx.register("get_stadium_name", m.get_stadium_name)
    ctx.register("livecpk_data_ready", m.data_ready)
    ctx.register("set_teams", m.match_setup)
    ctx.register("after_set_conditions", m.match_setup)
    ctx.register("context_reset", m.context_reset)
    log("[ucl36] ucl36_guard " .. m.version .. " attivo")
end

return m
