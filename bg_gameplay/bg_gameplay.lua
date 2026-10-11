-- bg_gameplay.lua  -  зарежда bg_gameplay.dll: настройки на геймплея от bg_gameplay.ini + Fair Rating (PES 2021, exe 1.01)
-- Изисква в sider.ini: luajit.ext.enabled = 1
-- DLL-ът и bg_gameplay.ini са в папката modules на Sider. Настройките се четат наново преди всеки мач.
-- В sider.log се пише само при проблем; ако няма редове с bg_gameplay, всичко е сложено.

local m = {}

local EN = false   -- true = English texts

local function T(bg, en) if EN then return en end return bg end

local dll_log, dll_reload, logbuf

local function drain()
    if not dll_log then return end
    for _ = 1, 32 do
        local n = tonumber(dll_log(logbuf, 4096))
        if n <= 0 then break end
        for line in ffi.string(logbuf, n):gmatch("[^\n]+") do log(line) end
    end
end

function m.set_teams(ctx, home, away)
    if dll_reload then dll_reload(tonumber(home) or 0, tonumber(away) or 0) end
    drain()
end

function m.init(ctx)
    if ffi == nil then log(T("bg_gameplay: няма ffi -- сложи luajit.ext.enabled = 1 в sider.ini", "bg_gameplay: no ffi -- set luajit.ext.enabled = 1 in sider.ini")); return end
    ffi.cdef([[
        void* LoadLibraryA(const char*);
        void* GetProcAddress(void*, const char*);
        void* GetModuleHandleA(const char*);
        unsigned long GetLastError(void);
        typedef int  (*bg_gameplay_install_t)(uint64_t, const char*);
        typedef void (*bg_gameplay_reload_t)(uint32_t, uint32_t);
        typedef int  (*bg_gameplay_log_t)(char*, int);
    ]])
    local sep = string.char(92)
    local dir = ctx.sider_dir:gsub("[/" .. sep .. "]+$", "") .. sep .. "modules" .. sep
    local h = ffi.C.LoadLibraryA(dir .. "bg_gameplay.dll")
    if h == nil then
        log(string.format(T("bg_gameplay: не се зареди %sbg_gameplay.dll (грешка %d)", "bg_gameplay: could not load %sbg_gameplay.dll (error %d)"), dir, tonumber(ffi.C.GetLastError())))
        return
    end
    local pi = ffi.C.GetProcAddress(h, "bg_gameplay_install")
    local pr = ffi.C.GetProcAddress(h, "bg_gameplay_reload")
    local pl = ffi.C.GetProcAddress(h, "bg_gameplay_log")
    if pi == nil or pr == nil or pl == nil then log(T("bg_gameplay: DLL-ът няма нужните функции", "bg_gameplay: the DLL lacks the needed functions")); return end
    dll_log = ffi.cast("bg_gameplay_log_t", pl)
    logbuf = ffi.new("char[4096]")

    local base = ffi.cast("uint64_t", ffi.C.GetModuleHandleA(nil))
    local status = tonumber(ffi.cast("bg_gameplay_install_t", pi)(base, dir .. "bg_gameplay.ini"))
    drain()
    if status ~= 0 then
        log(string.format(T("bg_gameplay: НЕ е инсталиран (код %d) -- играта е непроменена", "bg_gameplay: NOT installed (code %d) -- the game is unchanged"), status))
        return
    end
    dll_reload = ffi.cast("bg_gameplay_reload_t", pr)
    ctx.register("set_teams", m.set_teams)
end

return m
