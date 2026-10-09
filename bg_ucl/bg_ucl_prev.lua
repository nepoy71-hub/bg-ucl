-- bg_ucl.lua  -  зарежда bg_ucl.dll: UCL и UEL в новия формат (лигова фаза от 36)
-- Изисква в sider.ini: luajit.ext.enabled = 1
-- F8 пише в sider.log какво е направил DLL-ът до момента.

local m = {}

local dll_log, dll_stats, dll_tick, logbuf, statbuf
local ticks = 0

local function drain(reason)
    if not dll_log then return end
    for _ = 1, 32 do
        local n = tonumber(dll_log(logbuf, 4096))
        if n <= 0 then break end
        for line in ffi.string(logbuf, n):gmatch("[^\n]+") do log(line) end
    end
    if reason then
        dll_stats(statbuf)
        log(string.format("bg_ucl: %s -- лигови фази %d, дати %d, плейофи изтеглени %d, плейофи завършени %d, схеми подредени %d",
            reason, tonumber(statbuf[0]), tonumber(statbuf[1]), tonumber(statbuf[2]),
            tonumber(statbuf[3]), tonumber(statbuf[4])))
    end
end

function m.make_key(ctx, filename)
    ticks = ticks + 1
    if dll_tick and ticks % 64 == 0 then dll_tick() end
    if ticks % 32 == 0 then drain(nil) end
    return nil
end

function m.key_down(ctx, vkey)
    if vkey == 0x77 then drain("F8") end
end

function m.init(ctx)
    if ffi == nil then log("bg_ucl: няма ffi -- сложи luajit.ext.enabled = 1 в sider.ini"); return end
    ffi.cdef([[
        void* LoadLibraryA(const char*);
        void* GetProcAddress(void*, const char*);
        void* GetModuleHandleA(const char*);
        unsigned long GetLastError(void);
        typedef int  (*bg_ucl_install_t)(uint64_t);
        typedef int  (*bg_ucl_log_t)(char*, int);
        typedef void (*bg_ucl_stats_t)(uint32_t*);
        typedef void (*bg_ucl_tick_t)(void);
    ]])
    local sep = string.char(92)
    local path = ctx.sider_dir:gsub("[/" .. sep .. "]+$", "") .. sep .. "modules" .. sep .. "bg_ucl.dll"
    local h = ffi.C.LoadLibraryA(path)
    if h == nil then
        log(string.format("bg_ucl: не се зареди %s (грешка %d)", path, tonumber(ffi.C.GetLastError())))
        return
    end
    local pi = ffi.C.GetProcAddress(h, "bg_ucl_install")
    local pl = ffi.C.GetProcAddress(h, "bg_ucl_log")
    local ps = ffi.C.GetProcAddress(h, "bg_ucl_stats")
    local pt = ffi.C.GetProcAddress(h, "bg_ucl_tick")
    if pi == nil or pl == nil or ps == nil or pt == nil then log("bg_ucl: DLL-ът няма нужните функции"); return end
    dll_log = ffi.cast("bg_ucl_log_t", pl)
    dll_stats = ffi.cast("bg_ucl_stats_t", ps)
    logbuf, statbuf = ffi.new("char[4096]"), ffi.new("uint32_t[5]")

    local base = ffi.cast("uint64_t", ffi.C.GetModuleHandleA(nil))
    local status = tonumber(ffi.cast("bg_ucl_install_t", pi)(base))
    drain(nil)
    if status ~= 0 then
        log("bg_ucl: НЕ е инсталиран (код " .. status .. ") -- играта е непроменена")
        return
    end
    dll_tick = ffi.cast("bg_ucl_tick_t", pt)
    ctx.register("livecpk_make_key", m.make_key)
    ctx.register("key_down", m.key_down)
    log("bg_ucl: готов (F8 = отчет)")
end

return m
